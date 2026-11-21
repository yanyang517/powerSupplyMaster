"""Server 进程级运行时配置：电源设置命令的动态限值。

限值在此集中定义，handler 在每次请求时读取，
因此未来 UI 动态修改只需更新 runtime_config 字段。
"""
from dataclasses import dataclass

# TCP 控制服务的监听端口；8888 是最常被占用的开发备用端口，避开它。
SERVER_PORT = 18888


@dataclass
class RuntimeConfig:
    max_voltage: float = 30.0
    max_current: float = 5.0


runtime_config = RuntimeConfig()
