"""MCP 工具定义：电源设备的 4 个语义化工具（design D4/D8）。

桥接层不持有业务规则：限值校验、连接状态判断都在 SocketServer 端，
本模块只负责转发请求并把服务端结果翻译成 AI 可读的成功/错误信息。
"""
import logging
from typing import Any, Dict, Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .psu_client import PsuAccessDeniedError, PsuClient, PsuUnavailableError

logger = logging.getLogger(__name__)

mcp = MCPServer(
    "power-supply",
    instructions=(
        "控制一台实验室 SCPI 电源。串口连接由 powerSupplyMaster 桌面应用的 UI 管理，"
        "这些工具只操作已连接的设备；遇到“设备未连接”提示时请让用户在 UI 中连接。"
        "设定电压/电流前先用 get_status 读取 limits 中的允许范围。"
    ),
)

client = PsuClient()


async def _request(request_type: str, **fields: Any) -> Dict[str, Any]:
    try:
        response = await client.request(request_type, **fields)
    except PsuUnavailableError as e:
        raise ToolError(
            f"电源控制应用未运行或连接中断。请先启动 powerSupplyMaster（默认监听 127.0.0.1:18888），再重试。({e})"
        )
    except PsuAccessDeniedError as e:
        raise ToolError(
            "电源控制应用拒绝了本桥的登录：该 client_id 未登记，且当前没有可批准的界面会话。"
            f"请在 powerSupplyMaster 的界面中确认准入，或把 client_id 加入登记表。({e})"
        )
    if "status" not in response and "error" in response:
        raise ToolError(f"server 处理失败: {response.get('error')} {response.get('message', '')}".strip())
    if response.get("status") != "success":
        message = response.get("message") or "unknown error"
        if "device not connected" in message:
            raise ToolError("设备未连接。请先在 powerSupplyMaster 的 UI 中连接电源串口，然后再试。")
        raise ToolError(message)
    return response


@mcp.tool()
async def get_status() -> Dict[str, Any]:
    """读取电源当前状态：电压、电流、输出开关、设备标识与生效的限值范围。

    只读操作，不会改变设备状态。设定类工具的允许范围以返回的 limits 为准；
    limits.server_version 是正在控制这台电源的上位机版本，报障时以它为准，
    读不到（为 null）说明对端是尚未上报版本号的老版本。
    执行 set_output 前应先调用本工具确认当前状态。
    """
    identifier = (await _request("device_id_query")).get("value")
    voltage = (await _request("voltage_query")).get("value")
    current = (await _request("current_query")).get("value")
    output_on = (await _request("on_off_query")).get("value")

    limits: Optional[Dict[str, Any]] = None
    try:
        setting = await client.request("setting_query")
        if setting.get("status") == "success":
            limits = {
                "max_voltage_v": setting.get("max_voltage"),
                "max_current_a": setting.get("max_current"),
                "server_version": setting.get("version"),
            }
    except Exception as e:  # 限值是附加信息，失败不阻断状态读取
        logger.info(f"setting_query unavailable: {e}")

    return {
        "identifier": identifier,
        "voltage_v": voltage,
        "current_a": current,
        "output_on": output_on,
        "limits": limits,
    }


@mcp.tool()
async def set_voltage(voltage: float) -> Dict[str, Any]:
    """设定电源输出电压（单位 V）。

    允许范围以 get_status 返回的 limits.max_voltage_v 为准（下限 0）；
    超限请求会被服务端拒绝并在错误信息中给出允许范围，请据此修正后重试。
    """
    response = await _request("set_voltage", value=voltage)
    return {"set_voltage_v": response.get("value")}


@mcp.tool()
async def set_current(current: float) -> Dict[str, Any]:
    """设定电源输出电流限流值（单位 A）。

    允许范围以 get_status 返回的 limits.max_current_a 为准（下限 0）；
    超限请求会被服务端拒绝并在错误信息中给出允许范围，请据此修正后重试。
    """
    response = await _request("set_current", value=current)
    return {"set_current_a": response.get("value")}


@mcp.tool()
async def set_output(enable: bool) -> Dict[str, Any]:
    """接通（true）或断开（false）电源输出。

    警告：接通后负载立即带电。调用前应先用 get_status 确认当前电压/电流与输出状态，
    并确保电压设定合理。设备未连接时会失败并提示。
    """
    await _request("set_on_off", value=enable)
    status = await _request("on_off_query")
    return {"output_on": status.get("value")}
