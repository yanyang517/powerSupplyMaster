"""Server 进程级运行时配置：电源设置命令的动态限值与 TCP 控制服务的绑定地址。

限值与校验在此集中定义，GUI、TCP/MCP handler 每次写入前读取同一份配置。
"""
import ipaddress
from dataclasses import dataclass
import math
from typing import Literal

# TCP 控制服务的监听端口；8888 是最常被占用的开发备用端口，避开它。
SERVER_PORT = 18888

# 默认只绑回环。准入层是「名单 + 等级 + 租约」，不是认证：client_id 由客户端自报，
# 能连上端口就等于能冒充名单里的身份（见 registry.py 明确拒绝凭据字段）。所以跨机
# 暴露必须是显式决定（--listen 0.0.0.0），且仅适用于隔离、可信的内网实验环境。
SERVER_HOST = "127.0.0.1"

# 无认证的内网准入必须有资源上界。这些是固定的保守上限，不随客户端请求放宽。
MAX_CLIENT_ID_LENGTH = 128
MAX_REGISTRY_CLIENTS = 100
MAX_ADMISSION_ATTEMPTS = 10
ADMISSION_RATE_WINDOW_SECONDS = 60.0


def is_loopback_host(host: object) -> bool:
    """Return whether a bind host is known to be loopback-only.

    Unknown, malformed, empty, wildcard, and non-IP host names fail closed as
    exposed. ``localhost`` is the sole name accepted as loopback; all other
    names are warned about even if they happen to resolve locally.
    """
    if not isinstance(host, str) or not host.strip():
        return False
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass
class RuntimeConfig:
    max_voltage: float = 30.0
    max_current: float = 5.0


runtime_config = RuntimeConfig()

SettingName = Literal["voltage", "current"]
LimitErrorCode = Literal["negative", "over_limit", "non_finite", "invalid_limit"]


class SetpointLimitError(ValueError):
    """一次设置值校验失败；GUI 与 TCP 响应共用同一份结构化详情。"""

    def __init__(self, setting: SettingName, value: float, *,
                 code: LimitErrorCode, limit: float):
        self.setting = setting
        self.value = value if math.isfinite(value) else repr(value)
        self.code = code
        self.limit = limit
        # 非有限限值不能放进 JSON 数值字段；用字符串保留诊断信息。
        self.maximum = limit if math.isfinite(limit) else repr(limit)
        self.unit = "V" if setting == "voltage" else "A"
        precision = 2 if setting == "voltage" else 3
        limit_text = f"{limit:.{precision}f}" if math.isfinite(limit) else repr(limit)
        value_text = f"{value:.{precision}f}" if math.isfinite(value) else repr(value)
        if code == "invalid_limit":
            message = (
                f"configured max_{setting} limit {limit_text}{self.unit} is invalid; "
                f"refusing {setting} {value_text}{self.unit}"
            )
        else:
            message = (
                f"{setting} {value_text}{self.unit} out of allowed range "
                f"0~{limit_text}{self.unit}"
            )
        super().__init__(message)

    def as_dict(self) -> dict[str, str | float]:
        return {
            "code": self.code,
            "setting": self.setting,
            "value": self.value,
            "minimum": 0.0,
            "maximum": self.maximum,
            "unit": self.unit,
            "message": str(self),
        }


def validate_power_limit(setting: SettingName, value: float) -> float:
    """校验一个配置上限；只接受有限非负数，0 表示仅允许零设置。"""
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            f"max_{setting} must be a finite non-negative number, got {value!r}"
        ) from exc
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(
            f"max_{setting} must be a finite non-negative number, got {value!r}"
        )
    return numeric


def configure_runtime_limits(max_voltage: float, max_current: float) -> None:
    """原子更新运行时限值；任一无效时保持原配置不变。"""
    voltage = validate_power_limit("voltage", max_voltage)
    current = validate_power_limit("current", max_current)
    runtime_config.max_voltage = voltage
    runtime_config.max_current = current


def normalize_power_setting(setting: SettingName, value: float, unit: str) -> float:
    """把请求声明单位换算为 V/A 后，再执行统一限值校验。"""
    default_unit = "V" if setting == "voltage" else "A"
    scaled_unit = "mV" if setting == "voltage" else "mA"
    if unit == default_unit:
        return validate_power_setting(setting, value)
    if unit == scaled_unit:
        return validate_power_setting(setting, float(value) / 1000.0)
    raise ValueError(f"unsupported {setting} unit: {unit!r}")


def validate_power_setting(setting: SettingName, value: float) -> float:
    """返回可下发的有限非负值，否则抛出带稳定错误码的异常。

    下限包含 0，上限包含运行时限值。配置限值自身无效时优先拒绝，不能把
    NaN 上限误当成放行条件。NaN 与正负无穷设置值也显式拒绝。
    """
    raw_limit = getattr(runtime_config, f"max_{setting}")
    try:
        limit = validate_power_limit(setting, raw_limit)
    except ValueError as exc:
        try:
            diagnostic_limit = float(raw_limit)
        except (TypeError, ValueError, OverflowError):
            diagnostic_limit = float("nan")
        try:
            diagnostic_value = float(value)
        except (TypeError, ValueError, OverflowError):
            diagnostic_value = float("nan")
        raise SetpointLimitError(
            setting, diagnostic_value, code="invalid_limit", limit=diagnostic_limit,
        ) from exc

    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SetpointLimitError(
            setting, float("nan"), code="non_finite", limit=limit,
        ) from exc

    if not math.isfinite(numeric):
        raise SetpointLimitError(setting, numeric, code="non_finite", limit=limit)
    if numeric < 0:
        raise SetpointLimitError(setting, numeric, code="negative", limit=limit)
    if numeric > limit:
        raise SetpointLimitError(setting, numeric, code="over_limit", limit=limit)
    return numeric
