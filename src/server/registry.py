"""客户端登记表：身份准入名单与授权等级。

登记表是准入名单而非凭据库：client_id 由客户端自报，本模块 MUST NOT 接收
口令、密钥或证书字段（见 server/client-access-control 规格）。
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
CONFIG_DIR_NAME = "config"
CLIENTS_FILE_NAME = "clients.json"

_FORBIDDEN_FIELDS = {"password", "token", "secret", "key", "api_key", "apikey", "credential"}


class Tier(IntEnum):
    """命令授权等级，数值可直接比较大小。"""

    L0 = 0
    L1 = 1
    L2 = 2

    @property
    def needs_lease(self) -> bool:
        return self >= Tier.L1

    @classmethod
    def parse(cls, value: object) -> "Tier":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            text = value.strip().upper()
            try:
                return cls[text]
            except KeyError:
                raise RegistryError(f"unknown tier {value!r}, expected one of L0/L1/L2") from None
        raise RegistryError(f"tier must be a string, got {type(value).__name__}")


class RegistryError(Exception):
    """登记表不可用：文件缺失、不可解析或字段非法。"""


@dataclass(frozen=True)
class Principal:
    client_id: str
    tier: Tier
    name: str

    def to_entry(self) -> dict:
        return {"tier": self.tier.name, "name": self.name}


def clients_file_path(module_file: str = __file__) -> Path:
    """登记表路径，与进程 cwd 无关；冻结运行时落在可执行文件同级目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / CONFIG_DIR_NAME / CLIENTS_FILE_NAME
    return Path(module_file).resolve().parents[2] / CONFIG_DIR_NAME / CLIENTS_FILE_NAME


def _require_str(entry: dict, field: str, client_id: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RegistryError(f"client {client_id!r} field {field!r} must be a non-empty string")
    return value.strip()


def _validate_entry(client_id: str, entry: object) -> Principal:
    if not isinstance(client_id, str) or not client_id.strip():
        raise RegistryError(f"client id must be a non-empty string, got {client_id!r}")
    if not isinstance(entry, dict):
        raise RegistryError(f"client {client_id!r} must map to an object, got {type(entry).__name__}")

    forbidden = _FORBIDDEN_FIELDS & {key.lower() for key in entry}
    if forbidden:
        raise RegistryError(
            f"client {client_id!r} carries credential field(s) {sorted(forbidden)}; "
            "the registry is an allow-list, not a secret store"
        )

    return Principal(
        client_id=client_id.strip(),
        tier=Tier.parse(entry.get("tier")),
        name=_require_str(entry, "name", client_id),
    )


def parse_registry(raw: str, source: str) -> dict[str, Principal]:
    """把登记表 JSON 文本解析为 client_id -> Principal，任何非法输入都报错。"""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RegistryError(f"{source} is not valid JSON: {e}") from e

    if not isinstance(data, dict):
        raise RegistryError(f"{source} must contain a JSON object, got {type(data).__name__}")

    version = data.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise RegistryError(f"{source} has unsupported schema_version {version!r}, expected {SCHEMA_VERSION}")

    clients = data.get("clients")
    if clients is None:
        raise RegistryError(f"{source} is missing the 'clients' object")
    if not isinstance(clients, dict):
        raise RegistryError(f"{source} 'clients' must be an object keyed by client_id")

    return {client_id: _validate_entry(client_id, entry) for client_id, entry in clients.items()}


class ClientRegistry:
    """登记表：加载、查询与新增落盘。"""

    def __init__(self, path: Path, principals: dict[str, Principal]):
        self.path = path
        self._principals = principals

    @classmethod
    def load(cls, path: Path | None = None) -> "ClientRegistry":
        file_path = path or clients_file_path()
        if not file_path.is_file():
            raise RegistryError(
                f"client registry not found: {file_path}. "
                "Create it with {\"schema_version\": 1, \"clients\": {...}} or pass --clients."
            )
        try:
            raw = file_path.read_text(encoding="utf-8")
        except OSError as e:
            raise RegistryError(f"cannot read client registry {file_path}: {e}") from e

        principals = parse_registry(raw, str(file_path))
        logger.info("loaded %d client(s) from %s", len(principals), file_path)
        return cls(file_path, principals)

    def get(self, client_id: str) -> Principal | None:
        if not isinstance(client_id, str):
            return None
        return self._principals.get(client_id.strip())

    def add(self, principal: Principal) -> bool:
        """新增或覆盖一个登记项并写回文件；返回是否改变了内容。"""
        existing = self._principals.get(principal.client_id)
        if existing == principal:
            return False
        self._principals[principal.client_id] = principal
        self.save()
        logger.info("client %r registered at tier %s", principal.client_id, principal.tier.name)
        return True

    def save(self) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "clients": {cid: p.to_entry() for cid, p in sorted(self._principals.items())},
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # 半截文件会让下次启动直接失败，所以先写临时文件再原子替换。
        fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), prefix=self.path.name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp_name, self.path)
        except OSError:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def __iter__(self) -> Iterator[Principal]:
        return iter(self._principals[cid] for cid in sorted(self._principals))

    def __len__(self) -> int:
        return len(self._principals)


_registry: ClientRegistry | None = None


def use_registry(registry: ClientRegistry) -> None:
    """由启动入口注入进程级登记表。"""
    global _registry
    _registry = registry


def get_registry() -> ClientRegistry:
    if _registry is None:
        raise RegistryError("client registry is not loaded; call use_registry() at startup")
    return _registry
