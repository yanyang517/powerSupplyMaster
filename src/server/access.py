"""授权判定：认证 -> 命令等级 -> 独占控制权。

三道门相互独立：等级不足与控制权被占用是两种不同的拒绝，响应必须分别说明，
否则客户端无法判断该申请提权还是该等待对方交还。
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Callable

from .registry import Principal, RegistryError, Tier, get_registry, normalize_client_id
from .runtime_config import (
    ADMISSION_RATE_WINDOW_SECONDS,
    MAX_ADMISSION_ATTEMPTS,
    MAX_REGISTRY_CLIENTS,
)
from .session import LeaseReservation, PendingApproval, Session, access_config, lease, pending_approvals

logger = logging.getLogger(__name__)

audit_logger = logging.getLogger("server.audit")


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""
    message: str = ""
    reservation: LeaseReservation | None = None

    @property
    def denied(self) -> bool:
        return not self.allowed


ALLOW = Decision(True)


@dataclass(frozen=True)
class Admission:
    granted: bool
    principal: Principal | None = None
    reason: str = ""
    message: str = ""


class AdmissionRateLimiter:
    """Process-wide sliding window for first-contact admission attempts."""

    def __init__(
        self,
        max_attempts: int = MAX_ADMISSION_ATTEMPTS,
        window_seconds: float = ADMISSION_RATE_WINDOW_SECONDS,
    ):
        if max_attempts < 1 or window_seconds <= 0:
            raise ValueError("admission rate limit must be positive")
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: deque[float] = deque()

    def _purge(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._attempts and self._attempts[0] <= cutoff:
            self._attempts.popleft()

    def allow(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        self._purge(now)
        if len(self._attempts) >= self.max_attempts:
            return False
        self._attempts.append(now)
        return True

    def retry_after_seconds(self, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        self._purge(now)
        if len(self._attempts) < self.max_attempts:
            return 0.0
        return max(0.0, self._attempts[0] + self.window_seconds - now)

    def reset(self) -> None:
        self._attempts.clear()


admission_rate_limiter = AdmissionRateLimiter()


def _allow() -> Decision:
    return ALLOW


def evaluate(session: Session, command: str, tier: Tier) -> Decision:
    """业务命令的三道门；public 命令（登录、探活）不经过此函数。"""
    if not session.is_authenticated:
        return Decision(
            False,
            "not_authenticated",
            f"command {command!r} requires login; send {{\"type\":\"login\",\"client_id\":...}} first",
        )

    if tier > session.tier:
        return Decision(
            False,
            "insufficient_tier",
            f"command {command!r} needs {tier.name} but client {session.client_id!r} is {session.tier.name}",
        )

    if not tier.needs_lease:
        return _allow()

    return _lease_decision(session, command)


def _lease_decision(session: Session, command: str) -> Decision:
    holder = lease.holder
    client_id = session.client_id
    if holder is None or holder == client_id:
        # 隐式预留：在进入处理器前独占控制权，成功提交、失败回滚。
        reservation = lease.reserve(client_id, session.tier)
        if reservation is None:
            return Decision(False, "lease_lost", f"command {command!r} lost the lease race; retry")
        return Decision(True, reservation=reservation)

    snap = lease.snapshot()
    return Decision(
        False,
        "controlled_by_other",
        (
            f"device is under control of {holder!r} "
            f"(idle {snap.since_last_write_seconds:.0f}s of {snap.remaining_seconds:.0f}s left); "
            f"command {command!r} not executed"
        ),
    )


def commit_write(reservation: LeaseReservation | None) -> bool:
    """成功落地的写操作提交预留并为控制权续期。"""
    return reservation is not None and lease.commit(reservation)


def rollback_write(reservation: LeaseReservation | None) -> bool:
    """确定未写入的失败请求回滚本次新建的预留。"""
    return reservation is not None and lease.rollback(reservation)


def quarantine_write(reservation: LeaseReservation | None, reason: str) -> bool:
    """写入结果不明时隔离预留，避免立即把设备交给另一个客户端。"""
    return reservation is not None and lease.quarantine(reservation, reason)


def panel_revoke() -> str | None:
    """面板强制吊销：空闲时立即释放，在途/隔离时拒绝并审计，设备输出不动。"""
    holder = lease.revoke()
    if holder is not None:
        audit_logger.warning("ACCESS origin=panel cmd=revoke_lease revoked=%s result=success",
                             holder)
    elif lease.reservation_busy:
        audit_logger.warning("ACCESS origin=panel cmd=revoke_lease result=busy holder=%s",
                             lease.holder)
    return holder


def audit(session: Session, command: str, tier: Tier | None, decision: Decision,
          handler_status: str | None = None) -> None:
    """每次判定留痕；被拒记录同样重要，它回答"谁想做什么被挡住了"。"""
    fields = (
        f"session={session.session_id}",
        f"peer={session.peer}",
        f"client={session.client_id or '-'}",
        f"tier={tier.name if tier else '-'}",
        f"cmd={command}",
    )
    if decision.allowed:
        outcome = f"allowed result={handler_status or 'ok'}"
        audit_logger.info("ACCESS %s %s", " ".join(fields), outcome)
    else:
        holder = lease.holder if decision.reason == "controlled_by_other" else None
        extra = f" holder={holder!r}" if holder else ""
        audit_logger.warning("ACCESS %s denied reason=%s msg=%s%s",
                             " ".join(fields), decision.reason, decision.message, extra)


def audit_admission(client_id: str, tier: Tier, reason: str, granted: bool) -> None:
    """准入决定单独留痕：它回答"谁被谁放进来/挡住"。"""
    line = f"ADMISSION client={client_id} tier={tier.name} {'granted' if granted else 'refused'} reason={reason}"
    (audit_logger.info if granted else audit_logger.warning)(line)


_approval_handler: Callable[[PendingApproval], None] | None = None


def set_approval_handler(handler: Callable[[PendingApproval], None] | None) -> None:
    """带界面的启动路径注册确认回调；--no-gui 下保持为空。"""
    global _approval_handler
    _approval_handler = handler


def has_approver() -> bool:
    return _approval_handler is not None


async def admit(session: Session, client_id: str, requested_tier: Tier) -> Admission:
    """首次准入：已登记直接登录，新身份受全局限速与登记表容量约束。"""
    try:
        client_id = normalize_client_id(client_id)
    except RegistryError as e:
        return Admission(False, None, "invalid_client_id", str(e))

    registry = get_registry()

    known = registry.get(client_id)
    if known is not None:
        if known.tier < requested_tier:
            session.principal = known
            return Admission(True, known, "registered",
                             f"granted {known.tier.name} as registered (requested {requested_tier.name})")
        return Admission(True, known, "registered", "")

    if len(registry) >= MAX_REGISTRY_CLIENTS:
        message = (
            f"client registry is full (maximum {MAX_REGISTRY_CLIENTS} entries); "
            "remove unused entries before admitting new clients"
        )
        audit_admission(client_id, requested_tier, "registry_full", False)
        return Admission(False, None, "registry_full", message)

    if not admission_rate_limiter.allow():
        retry_after = admission_rate_limiter.retry_after_seconds()
        message = (
            f"too many first-contact admission attempts; retry after "
            f"{max(1, round(retry_after))} second(s)"
        )
        audit_admission(client_id, requested_tier, "rate_limited", False)
        return Admission(False, None, "rate_limited", message)

    if requested_tier is Tier.L0:
        principal = Principal(client_id, Tier.L0, client_id)
        try:
            registry.add(principal)
        except RegistryError as e:
            audit_admission(client_id, Tier.L0, "registry_full", False)
            return Admission(False, None, "registry_full", str(e))
        audit_admission(client_id, Tier.L0, "auto_admitted_l0", True)
        return Admission(True, principal, "auto_admitted_l0", "")

    if _approval_handler is None:
        return Admission(False, None, "no_approver",
                         f"L1/L2 admission for {client_id!r} needs the panel confirmation dialog "
                         "or a pre-filled registry")

    loop = asyncio.get_running_loop()
    approval = PendingApproval(
        request_id=str(uuid.uuid4())[:8],
        client_id=client_id,
        tier=requested_tier,
        peer=session.peer,
        future=loop.create_future(),
    )
    pending_approvals.add(approval)
    _approval_handler(approval)
    logger.info("admission pending for %r at %s (request %s)", client_id, requested_tier.name, approval.request_id)

    try:
        approved = await asyncio.wait_for(approval.future, access_config.approval_timeout_seconds)
        reason = "approved_by_user" if approved else "refused_by_user"
    except TimeoutError:
        approved = False
        reason = "approval_timeout"
    finally:
        pending_approvals.discard(approval.request_id)

    audit_admission(client_id, requested_tier, reason, approved)
    if not approved:
        session.close_after_response = True
        return Admission(False, None, reason, f"admission {reason.replace('_', ' ')}")

    principal = Principal(client_id, requested_tier, client_id)
    try:
        registry.add(principal)
    except RegistryError as e:
        audit_admission(client_id, requested_tier, "registry_full", False)
        return Admission(False, None, "registry_full", str(e))
    return Admission(True, principal, reason, "")

