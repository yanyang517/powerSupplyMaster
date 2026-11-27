"""会话与控制权状态：连接身份、活动会话表、独占控制权租约。

控制权归属于 client_id 而非连接（设计 D1）：客户端可以闪断重连而不丢权限，
崩溃的客户端则只保留到租约超时。
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Iterator

from .registry import Principal, Tier

logger = logging.getLogger(__name__)


@dataclass
class LeaseConfig:
    ttl_seconds: float = 120.0


lease_config = LeaseConfig()


@dataclass
class AccessConfig:
    approval_timeout_seconds: float = 60.0


access_config = AccessConfig()


def _now() -> float:
    return time.monotonic()


@dataclass
class Session:
    """一条 TCP 连接。断开即丢弃，与控制权生命周期无关。"""

    peer: str
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    principal: Principal | None = None
    connected_at: float = field(default_factory=time.time)
    connected_mono: float = field(default_factory=_now)
    # 准入被拒后由 handle_client 在写完响应时关闭连接
    close_after_response: bool = False

    @property
    def is_authenticated(self) -> bool:
        return self.principal is not None

    @property
    def client_id(self) -> str | None:
        return self.principal.client_id if self.principal else None

    @property
    def tier(self) -> Tier | None:
        return self.principal.tier if self.principal else None

    def authenticate(self, principal: Principal) -> None:
        self.principal = principal

    def logout(self) -> None:
        self.principal = None

    def uptime_seconds(self) -> float:
        return _now() - self.connected_mono

    def describe(self) -> dict:
        return {
            "session_id": self.session_id,
            "peer": self.peer,
            "client_id": self.client_id,
            "name": self.principal.name if self.principal else None,
            "tier": self.principal.tier.name if self.principal else None,
            "authenticated": self.is_authenticated,
            "uptime_seconds": round(self.uptime_seconds(), 1),
        }


class SessionHub:
    """进程内活动会话表。"""

    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def open(self, peer: str) -> Session:
        session = Session(peer=peer)
        self._sessions[session.session_id] = session
        logger.info("session %s opened from %s", session.session_id, peer)
        return session

    def close(self, session: Session) -> None:
        if self._sessions.pop(session.session_id, None) is not None:
            logger.info("session %s closed (client=%s)", session.session_id, session.client_id)

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def find_by_client(self, client_id: str) -> list[Session]:
        return [s for s in self._sessions.values() if s.client_id == client_id]

    def has_client(self, client_id: str) -> bool:
        return bool(self.find_by_client(client_id))

    def __iter__(self) -> Iterator[Session]:
        return iter(list(self._sessions.values()))

    def __len__(self) -> int:
        return len(self._sessions)


@dataclass(frozen=True)
class LeaseSnapshot:
    holder: str | None
    tier: str | None
    remaining_seconds: float
    held_seconds: float
    since_last_write_seconds: float
    last_written_at: float | None
    holder_connected: bool

    @property
    def is_held(self) -> bool:
        return self.holder is not None

    def describe(self) -> dict:
        return {
            "holder": self.holder,
            "tier": self.tier,
            "remaining_seconds": round(self.remaining_seconds, 1),
            "held_seconds": round(self.held_seconds, 1),
            "since_last_write_seconds": round(self.since_last_write_seconds, 1),
            "holder_connected": self.holder_connected,
        }


@dataclass(frozen=True)
class LeaseReservation:
    """一次写请求对控制权的预留；generation 防止旧请求释放新租约。"""

    client_id: str
    generation: int
    acquired: bool


@dataclass
class _ReservationState:
    active: int
    rollback_on_failure: bool
    quarantined_mono: float | None = None


class ControlLease:
    """单一电源的独占控制权；在途预留阻止到期，失败时按凭证回滚。"""

    def __init__(self, hub: "SessionHub | None" = None):
        self._holder: str | None = None
        self._holder_tier: Tier | None = None
        self._acquired_mono: float = 0.0
        self._last_write_mono: float = 0.0
        self._last_write_wall: float | None = None
        self._generation = 0
        self._reservations: dict[int, _ReservationState] = {}
        self.hub = hub

    def _pending_state(self) -> _ReservationState | None:
        return self._reservations.get(self._generation)

    def _expiry_mono(self, state: _ReservationState | None = None) -> float:
        pending = state or self._pending_state()
        if pending is not None and pending.quarantined_mono is not None:
            return pending.quarantined_mono
        return self._last_write_mono

    def _expire_if_stale(self) -> None:
        if self._holder is None:
            return
        pending = self._pending_state()
        if pending is not None and pending.active:
            # 执行中的写请求仍独占设备，不能因 TTL 到期而让第二个写入者进入。
            return
        if _now() - self._expiry_mono(pending) > lease_config.ttl_seconds:
            logger.info("control lease of %r expired", self._holder)
            self._clear()

    def _clear(self) -> None:
        self._generation += 1
        self._holder = None
        self._holder_tier = None
        self._acquired_mono = 0.0
        self._last_write_mono = 0.0
        self._last_write_wall = None
        self._reservations.clear()

    def _start_lease(self, client_id: str, tier: Tier) -> None:
        self._generation += 1
        self._reservations.clear()
        # 起算点放在认领时，之后每次成功写入续期；认领后一直不写也会到期释放。
        self._acquired_mono = _now()
        self._last_write_mono = self._acquired_mono
        self._last_write_wall = time.time()
        self._holder = client_id
        self._holder_tier = tier

    @property
    def holder(self) -> str | None:
        self._expire_if_stale()
        return self._holder

    @property
    def reservation_busy(self) -> bool:
        """仍有写请求在途，或结果不明、正在隔离等待对账/到期。"""
        self._expire_if_stale()
        pending = self._pending_state()
        return bool(pending and (pending.active or pending.quarantined_mono is not None))

    def is_held_by(self, client_id: str) -> bool:
        return self.holder == client_id

    def is_free(self) -> bool:
        return self.holder is None

    def claim(self, client_id: str, tier: Tier) -> bool:
        """空闲或本就由该客户端持有时成功；他人持有时失败。"""
        current = self.holder
        if current is not None and current != client_id:
            return False
        if current is None:
            self._start_lease(client_id, tier)
        else:
            self._holder_tier = tier
        return True

    def reserve(self, client_id: str, tier: Tier) -> LeaseReservation | None:
        """在调用处理器前原子预留控制权，并返回本次请求的所有权凭证。"""
        current = self.holder
        acquired = current is None
        if current is not None and current != client_id:
            return None
        if acquired:
            self._start_lease(client_id, tier)
        else:
            self._holder_tier = tier

        state = self._reservations.get(self._generation)
        if state is None:
            # 既有持有者（包括旧 claim 入口）不因一次失败而被释放。
            state = _ReservationState(active=0, rollback_on_failure=acquired)
            self._reservations[self._generation] = state
        state.active += 1
        return LeaseReservation(client_id, self._generation, acquired)

    def _reservation_state(self, reservation: LeaseReservation) -> _ReservationState | None:
        if (reservation.client_id != self._holder
                or reservation.generation != self._generation):
            return None
        return self._reservations.get(reservation.generation)

    def _finish_reservation(self, reservation: LeaseReservation) -> _ReservationState | None:
        state = self._reservation_state(reservation)
        if state is None or state.active <= 0:
            return None
        state.active -= 1
        return state

    def commit(self, reservation: LeaseReservation) -> bool:
        """成功写入提交预留并续期；过期或被吊销的凭证不得影响新持有者。"""
        state = self._reservation_state(reservation)
        if state is None or state.active <= 0:
            return False
        self._last_write_mono = _now()
        self._last_write_wall = time.time()
        state.rollback_on_failure = False
        state.quarantined_mono = None
        self._finish_reservation(reservation)
        if state.active == 0:
            self._reservations.pop(reservation.generation, None)
        return True

    def rollback(self, reservation: LeaseReservation) -> bool:
        """确定未写入的失败请求交还预留；隔离中的租约只能对账或等 TTL。"""
        state = self._finish_reservation(reservation)
        if state is None:
            return False
        if (state.active == 0 and state.rollback_on_failure
                and state.quarantined_mono is None):
            logger.info("control lease reservation of %r rolled back", reservation.client_id)
            self._clear()
        elif state.active == 0 and state.quarantined_mono is None:
            self._reservations.pop(reservation.generation, None)
        return True

    def quarantine(self, reservation: LeaseReservation, reason: str) -> bool:
        """取消、超时或异常可能发生在写入后，保留归属直到成功对账或 TTL。"""
        state = self._finish_reservation(reservation)
        if state is None:
            return False
        state.rollback_on_failure = False
        state.quarantined_mono = _now()
        logger.warning(
            "control lease of %r quarantined after uncertain write (%s); "
            "ownership retained until a successful write or TTL",
            reservation.client_id, reason,
        )
        return True

    def record_write(self, client_id: str) -> None:
        """只有成功写入才续期；旧 claim 入口的成功写入也可解除隔离。"""
        self._expire_if_stale()
        if self._holder != client_id:
            return
        self._last_write_mono = _now()
        self._last_write_wall = time.time()
        pending = self._pending_state()
        if pending is not None:
            pending.rollback_on_failure = False
            pending.quarantined_mono = None
            if pending.active == 0:
                self._reservations.pop(self._generation, None)

    def release(self, client_id: str) -> bool:
        """持有者主动交还；在途或隔离中的写请求不会被移交给竞争对手。"""
        if self.holder != client_id:
            return False
        if self.reservation_busy:
            logger.warning("control lease release by %r rejected: write reservation busy", client_id)
            return False
        self._clear()
        logger.info("control lease released by %r", client_id)
        return True

    def revoke(self) -> str | None:
        """面板强制吊销；有在途或结果不明的写入时拒绝，返回 None。"""
        current = self.holder
        if current is not None and self.reservation_busy:
            logger.warning("control lease revoke of %r rejected: write reservation busy", current)
            return None
        self._clear()
        if current:
            logger.info("control lease of %r revoked from panel", current)
        return current

    def snapshot(self) -> LeaseSnapshot:
        current = self.holder
        if current is None:
            return LeaseSnapshot(None, None, 0.0, 0.0, 0.0, None, False)
        ttl = lease_config.ttl_seconds
        idle = _now() - self._last_write_mono
        remaining = max(0.0, ttl - (_now() - self._expiry_mono()))
        return LeaseSnapshot(
            holder=current,
            tier=self._holder_tier.name if self._holder_tier else None,
            remaining_seconds=remaining,
            held_seconds=_now() - self._acquired_mono,
            since_last_write_seconds=idle,
            last_written_at=self._last_write_wall,
            holder_connected=bool(self.hub and self.hub.has_client(current)),
        )

    def seconds_remaining(self) -> float:
        return self.snapshot().remaining_seconds

    def describe(self) -> dict:
        return self.snapshot().describe()


hub = SessionHub()
lease = ControlLease(hub)


@dataclass
class PendingApproval:
    request_id: str
    client_id: str
    tier: Tier
    peer: str
    future: "asyncio.Future[bool]"
    requested_at: float = field(default_factory=time.time)

    def describe(self) -> dict:
        return {
            "request_id": self.request_id,
            "client_id": self.client_id,
            "tier": self.tier.name,
            "peer": self.peer,
            "requested_at": self.requested_at,
            "waiting_seconds": round(time.time() - self.requested_at, 1),
        }


class ApprovalQueue:
    """等待用户确认的准入请求。GUI 侧弹窗从这里取待办，决定是否后 resolve Future。"""

    def __init__(self):
        self._items: dict[str, PendingApproval] = {}

    def add(self, approval: PendingApproval) -> None:
        self._items[approval.request_id] = approval

    def discard(self, request_id: str) -> PendingApproval | None:
        return self._items.pop(request_id, None)

    def get(self, request_id: str) -> PendingApproval | None:
        return self._items.get(request_id)

    def decide(self, request_id: str, approved: bool) -> bool:
        """由用户应答调用；返回是否命中一个待确认项。"""
        approval = self._items.pop(request_id, None)
        if approval is None:
            return False
        if not approval.future.done():
            approval.future.set_result(approved)
        return True

    def __iter__(self) -> Iterator[PendingApproval]:
        return iter(list(self._items.values()))

    def __len__(self) -> int:
        return len(self._items)


pending_approvals = ApprovalQueue()
