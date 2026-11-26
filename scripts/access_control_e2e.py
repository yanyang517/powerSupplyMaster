"""端到端演示：三个客户端围绕一台电源的读取、持有与争用。

不依赖硬件：脚本自己在进程内起 SocketServer，并把 SCPI 设备假装成已连接，
因此它既是可复现的场景演示，也能当一次回归检查来跑。

运行方式（仓库根目录）：
    python scripts/access_control_e2e.py
    python scripts/access_control_e2e.py --port 18999 --lease-ttl 5
"""
import argparse
import asyncio
import json
import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from device.scpi_power_supply import SCPI_PowerSupply  # noqa: E402
from logging_config import configure_logging  # noqa: E402
from server.access import set_approval_handler  # noqa: E402
from server.registry import ClientRegistry, Tier, use_registry  # noqa: E402
from server.session import lease, lease_config  # noqa: E402
from server.socket_server import SocketServer  # noqa: E402

from mcp_server.psu_client import PsuAccessDeniedError, PsuClient  # noqa: E402

REGISTRY = {
    "schema_version": 1,
    "clients": {
        "watcher": {"tier": "L0", "name": "只读监控端"},
        "operator-a": {"tier": "L1", "name": "操作员 A"},
        "operator-b": {"tier": "L1", "name": "操作员 B"},
    },
}

FAILURES = []


def check(label, condition, detail=""):
    mark = "OK " if condition else "FAIL"
    print(f"[{mark}] {label}{('  -> ' + detail) if detail else ''}")
    if not condition:
        FAILURES.append(label)


def fake_device():
    """本脚本关心权限而不是串口：把设备单例假装成已连接。"""
    psu = SCPI_PowerSupply()
    psu.is_connected = True

    async def ignore(value):
        return None

    def reads(value):
        async def read():
            return value
        return read

    psu.set_voltage = ignore
    psu.set_current = ignore
    psu.set_on_off = ignore
    psu.get_voltage = reads(12.0)
    psu.get_current = reads(0.5)
    psu.get_on_off = reads(True)
    psu.get_identifier = reads("FAKE,RIGOL DP832")
    return psu


async def scenario(port: int, ttl: float, verbose: bool = False) -> None:
    lease_config.ttl_seconds = ttl
    registry_path = Path(tempfile.mkdtemp()) / "clients.json"
    registry_path.write_text(json.dumps(REGISTRY, ensure_ascii=False), encoding="utf-8")
    use_registry(ClientRegistry.load(registry_path))
    set_approval_handler(None)  # 无界面：未登记身份一律拒绝

    server = await asyncio.start_server(
        SocketServer(port=port).handle_client, "127.0.0.1", port)
    clients = [PsuClient(host="127.0.0.1", port=port, timeout=3.0, client_id=cid, tier=tier)
               for cid, tier in (("watcher", "L0"), ("operator-a", "L1"), ("operator-b", "L1"))]
    # 未登记身份：登录被拒后服务端会切断连接，但仍要由客户端自己关掉套接字
    stranger = PsuClient(host="127.0.0.1", port=port, timeout=3.0,
                         client_id="unknown-tool", tier="L1")

    try:
        watcher, operator_a, operator_b = clients
        print("\n--- 1) 三方登录 ---")
        for client in clients:
            status = await client.request("lease_status")
            check(f"{client.client_id} 已登录并可查询", status["status"] == "success")

        print("\n--- 2) 操作员 A 写入即认领控制权 ---")
        first = await operator_a.request("set_voltage", value=12.0)
        check("A 的首次写入成功", first["status"] == "success", str(first.get("message", "")))
        holder = (await operator_a.request("lease_status"))["holder"]
        check("控制权归属 A", holder == "operator-a", f"holder={holder}")

        print("\n--- 3) 只读不受控制权影响 ---")
        read = await watcher.request("voltage_query")
        check("B 之外的只读端仍能查询", read["status"] == "success", f"value={read.get('value')}")

        print("\n--- 4) 操作员 B 争用被拒，并被告知归属 ---")
        rival = await operator_b.request("set_voltage", value=24.0)
        check("B 的写入被拒", rival["status"] == "error", str(rival.get("message")))
        check("拒绝理由点名持有者 A", rival.get("message", "").find("operator-a") >= 0)

        print("\n--- 5) A 交还后 B 立即可认领 ---")
        released = await operator_a.request("release_lease")
        check("A 交还控制权", released["status"] == "success", str(released.get("message")))
        second = await operator_b.request("set_voltage", value=24.0)
        check("B 随即写入成功", second["status"] == "success", str(second.get("message")))
        holder = (await operator_b.request("lease_status"))["holder"]
        check("控制权现在属于 B", holder == "operator-b", f"holder={holder}")

        print("\n--- 6) B 停止写入后控制权按时限自动释放 ---")
        idle_holder = (await watcher.request("lease_status"))["holder"]
        check("仍在时限内，控制权尚未释放", idle_holder == "operator-b", f"holder={idle_holder}")
        await asyncio.sleep(ttl + 0.2)
        expired = await watcher.request("lease_status")
        check(f"闲置超过 {ttl:g}s 后自动释放", expired["holder"] is None,
              f"holder={expired['holder']}")

        print("\n--- 7) 未登记身份在无界面模式下直接被拒 ---")
        try:
            await stranger.request("voltage_query")
            check("未登记身份被拒", False, "竟然请求成功")
        except PsuAccessDeniedError as e:
            check("未登记身份被拒", "no_approver" in str(e), str(e))

        print("\n--- 8) 面板视角：谁是连接、谁是控制 ---")
        # 未登记的一方在断开前仍是"连接着但无身份"，面板要能把它和已授权者区分开
        pre_drop = await watcher.request("list_clients")
        check("被拒方在断开前只是未认证连接",
              len(pre_drop["clients"]) == 4
              and sum(1 for item in pre_drop["clients"] if not item["authenticated"]) == 1,
              str([(item["client_id"], item["authenticated"]) for item in pre_drop["clients"]]))
        await stranger._drop_connection()
        await asyncio.sleep(0.2)
        listing = await watcher.request("list_clients")
        if verbose:
            print(json.dumps(listing, ensure_ascii=False, indent=2, default=str))
        check("会话数与登记表身份一致", len(listing["clients"]) == 3,
              f"clients={len(listing['clients'])}")
        check("每条会话都带身份与等级",
              all(item["authenticated"] and item["tier"] for item in listing["clients"]),
              str([item["client_id"] for item in listing["clients"]]))
    finally:
        for client in clients + [stranger]:
            await client._drop_connection()
        lease.revoke()
        server.close()
        await server.wait_closed()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18999)
    parser.add_argument("--lease-ttl", type=float, default=3.0,
                        help="控制权时限（秒），演示用短值")
    parser.add_argument("--verbose", action="store_true", help="打印服务端日志")
    args = parser.parse_args()

    configure_logging()
    logging.getLogger().setLevel(logging.INFO if args.verbose else logging.ERROR)
    fake_device()
    asyncio.run(scenario(args.port, args.lease_ttl, args.verbose))

    if FAILURES:
        print(f"\n失败 {len(FAILURES)} 项：{', '.join(FAILURES)}")
        return 1
    print("\n全部场景符合预期")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
