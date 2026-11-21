"""探测相关的进程级配置。

仿 `server/runtime_config.py` 的写法：集中定义、运行期读取，将来 UI 里加编辑
入口时只需改这个对象的字段，不必动调用点。URL 在这里是唯一一处，发布流程的
回读校验（`scripts/gen_manifest.py --remote`）也从这里取，避免两处各写一份。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Source:
    name: str
    url: str


#: 顺序即优先级；实测记录见 doc/update_notice.md（Gitee raw 可用，
#: GitHub raw 在开发机握手超时，但仍是有外网限制之外的用户的合理备源）。
DEFAULT_SOURCES = (
    Source("gitee",
           "https://gitee.com/yanyang517/power-supply-master/raw/master/update/latest.json"),
    Source("github",
           "https://raw.githubusercontent.com/yanyang517/powerSupplyMaster/master/update/latest.json"),
)


@dataclass
class UpdateSettings:
    sources: tuple[Source, ...] = DEFAULT_SOURCES
    interval_seconds: float = 24 * 3600.0
    startup_delay_seconds: float = 5.0
    timeout_seconds: float = 5.0
    #: 由 --no-update-check 与状态文件里的 disabled 共同改写
    enabled: bool = True

    def source_names(self) -> tuple[str, ...]:
        return tuple(source.name for source in self.sources)


update_settings = UpdateSettings()
