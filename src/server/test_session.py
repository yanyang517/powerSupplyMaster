"""server/control-lease 会话与租约测试：续期、到期、与连接解耦。

运行方式（在仓库根目录）：python -m pytest src/server/test_session.py
"""
import pytest

from . import session as session_mod
from .registry import Principal, Tier
from .session import ControlLease, SessionHub, lease_config


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds: float):
        self.t += seconds


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(session_mod, "_now", c)
    return c


@pytest.fixture
def fresh_ttl(monkeypatch):
    monkeypatch.setattr(lease_config, "ttl_seconds", 120.0)


class TestSessionHub:
    def test_open_then_enumerate(self):
        hub = SessionHub()
        s = hub.open("127.0.0.1:52134")
        assert len(hub) == 1
        assert [sess.session_id for sess in hub] == [s.session_id]
        assert not s.is_authenticated and s.tier is None

    def test_authenticate_sets_effective_tier(self):
        hub = SessionHub()
        s = hub.open("127.0.0.1:1")
        s.authenticate(Principal("mcp-bridge", Tier.L1, "AI 助手"))
        assert s.is_authenticated and s.tier is Tier.L1 and s.client_id == "mcp-bridge"
        s.logout()
        assert not s.is_authenticated

    def test_close_removes_session(self):
        hub = SessionHub()
        s = hub.open("127.0.0.1:1")
        hub.close(s)
        assert len(hub) == 0
        assert hub.get(s.session_id) is None

    def test_find_by_client_lists_multiple_sessions(self):
        hub = SessionHub()
        a = hub.open("127.0.0.1:1")
        b = hub.open("127.0.0.1:2")
        p = Principal("probe", Tier.L0, "probe")
        a.authenticate(p)
        b.authenticate(p)
        assert len(hub.find_by_client("probe")) == 2
        assert hub.has_client("probe") and not hub.has_client("other")

    def test_describe_distinguishes_authenticated(self):
        hub = SessionHub()
        s = hub.open("127.0.0.1:9")
        assert s.describe()["authenticated"] is False
        s.authenticate(Principal("probe", Tier.L2, "probe"))
        d = s.describe()
        assert d["authenticated"] is True and d["tier"] == "L2" and d["client_id"] == "probe"


class TestLeaseClaim:
    def test_free_lease_is_claimed_by_first_writer(self, clock, fresh_ttl):
        lease = ControlLease()
        assert lease.is_free()
        assert lease.claim("a", Tier.L1)
        lease.record_write("a")
        assert lease.holder == "a"

    def test_other_client_cannot_claim_held_lease(self, clock, fresh_ttl):
        lease = ControlLease()
        lease.claim("a", Tier.L1)
        lease.record_write("a")
        assert lease.claim("b", Tier.L2) is False
        assert lease.holder == "a"

    def test_same_holder_reclaim_keeps_held_time(self, clock, fresh_ttl):
        lease = ControlLease()
        lease.claim("a", Tier.L1)
        lease.record_write("a")
        clock.advance(10)
        assert lease.claim("a", Tier.L1) is True
        assert lease.snapshot().held_seconds == pytest.approx(10, abs=0.1)

    def test_claim_alone_does_not_stop_expiry(self, clock, fresh_ttl):
        """仅认领而未成功写入，不能把控制权无限占着。"""
        lease = ControlLease()
        lease.claim("a", Tier.L1)
        clock.advance(lease_config.ttl_seconds + 1)
        assert lease.is_free()


class TestLeaseReservation:
    def test_reservation_is_visible_before_handler_and_blocks_other_client(self, clock, fresh_ttl):
        lease = ControlLease()
        reservation = lease.reserve("a", Tier.L1)
        assert reservation is not None and reservation.acquired is True
        assert lease.holder == "a"
        assert lease.reserve("b", Tier.L2) is None
        assert lease.commit(reservation) is True
        assert lease.holder == "a"
        clock.advance(lease_config.ttl_seconds + 1)
        assert lease.is_free()

    def test_failed_first_write_rolls_back_new_reservation(self, clock, fresh_ttl):
        lease = ControlLease()
        reservation = lease.reserve("a", Tier.L1)
        assert lease.rollback(reservation) is True
        assert lease.is_free()
        assert lease.reserve("b", Tier.L2) is not None

    def test_failed_existing_holder_does_not_release_or_renew(self, clock, fresh_ttl):
        lease = ControlLease()
        lease.claim("a", Tier.L2)
        lease.record_write("a")
        clock.advance(10)
        before = lease.snapshot()
        reservation = lease.reserve("a", Tier.L1)
        assert reservation is not None and reservation.acquired is False
        clock.advance(5)
        assert lease.rollback(reservation) is True
        after = lease.snapshot()
        assert after.holder == "a"
        assert after.last_written_at == before.last_written_at
        assert after.held_seconds == pytest.approx(15, abs=0.1)

    def test_active_reservation_does_not_expire_while_handler_runs(self, clock, fresh_ttl):
        lease = ControlLease()
        reservation = lease.reserve("a", Tier.L1)
        clock.advance(lease_config.ttl_seconds + 1)
        assert lease.holder == "a"
        assert lease.reserve("b", Tier.L2) is None
        assert lease.rollback(reservation) is True
        assert lease.is_free()

    def test_stale_reservation_cannot_release_or_renew_new_lease(self, clock, fresh_ttl):
        lease = ControlLease()
        old = lease.reserve("a", Tier.L1)
        assert lease.rollback(old) is True
        current = lease.reserve("a", Tier.L2)
        clock.advance(10)
        assert lease.rollback(old) is False
        assert lease.commit(old) is False
        assert lease.holder == "a"
        assert lease.snapshot().since_last_write_seconds == pytest.approx(10, abs=0.1)
        assert lease.commit(current) is True

    def test_overlapping_failures_release_only_after_last_request_finishes(self, clock, fresh_ttl):
        lease = ControlLease()
        first = lease.reserve("a", Tier.L1)
        second = lease.reserve("a", Tier.L2)
        assert lease.rollback(first) is True
        assert lease.holder == "a"
        assert lease.reserve("b", Tier.L2) is None
        assert lease.rollback(second) is True
        assert lease.is_free()

    def test_overlapping_success_keeps_lease_after_other_request_fails(self, clock, fresh_ttl):
        lease = ControlLease()
        first = lease.reserve("a", Tier.L1)
        second = lease.reserve("a", Tier.L2)
        assert lease.rollback(first) is True
        assert lease.holder == "a"
        clock.advance(10)
        assert lease.commit(second) is True
        assert lease.holder == "a"
        assert lease.snapshot().since_last_write_seconds == pytest.approx(0, abs=0.1)

    def test_uncertain_failure_quarantines_until_ttl_from_failure(self, clock, fresh_ttl):
        lease = ControlLease()
        reservation = lease.reserve("a", Tier.L1)
        clock.advance(lease_config.ttl_seconds + 5)
        assert lease.quarantine(reservation, "timeout") is True
        assert lease.holder == "a"
        assert lease.reservation_busy is True
        assert lease.reserve("b", Tier.L2) is None
        assert lease.release("a") is False
        assert lease.revoke() is None

        clock.advance(lease_config.ttl_seconds - 1)
        assert lease.holder == "a"
        assert lease.seconds_remaining() == pytest.approx(1, abs=0.1)
        clock.advance(2)
        assert lease.is_free()
        assert lease.reserve("b", Tier.L2) is not None

    def test_definite_failure_cannot_clear_another_requests_quarantine(self, clock, fresh_ttl):
        lease = ControlLease()
        uncertain = lease.reserve("a", Tier.L1)
        definite = lease.reserve("a", Tier.L2)
        assert lease.quarantine(uncertain, "cancelled") is True
        assert lease.rollback(definite) is True
        assert lease.holder == "a"
        assert lease.reservation_busy is True
        assert lease.reserve("b", Tier.L2) is None
        clock.advance(lease_config.ttl_seconds + 1)
        assert lease.is_free()

    def test_successful_retry_reconciles_quarantine_and_renews(self, clock, fresh_ttl):
        lease = ControlLease()
        uncertain = lease.reserve("a", Tier.L1)
        assert lease.quarantine(uncertain, "transport error") is True
        retry = lease.reserve("a", Tier.L2)
        clock.advance(10)
        assert lease.commit(retry) is True
        assert lease.reservation_busy is False
        clock.advance(lease_config.ttl_seconds - 1)
        assert lease.holder == "a"
        assert lease.release("a") is True

    def test_existing_holder_quarantine_does_not_renew_last_write(self, clock, fresh_ttl):
        lease = ControlLease()
        lease.claim("a", Tier.L2)
        lease.record_write("a")
        clock.advance(10)
        before = lease.snapshot()
        reservation = lease.reserve("a", Tier.L1)
        clock.advance(5)
        assert lease.quarantine(reservation, "timeout") is True
        after = lease.snapshot()
        assert after.holder == "a"
        assert after.last_written_at == before.last_written_at
        assert after.since_last_write_seconds == pytest.approx(15, abs=0.1)
        assert after.remaining_seconds == pytest.approx(lease_config.ttl_seconds, abs=0.1)


class TestLeaseExpiry:
    def test_write_renews(self, clock, fresh_ttl):
        lease = ControlLease()
        lease.claim("a", Tier.L1)
        for _ in range(3):
            clock.advance(100)
            lease.record_write("a")
            assert lease.holder == "a"

    def test_expiry_frees_lease(self, clock, fresh_ttl):
        lease = ControlLease()
        lease.claim("a", Tier.L1)
        lease.record_write("a")
        clock.advance(lease_config.ttl_seconds - 1)
        assert lease.holder == "a"
        clock.advance(2)
        assert lease.is_free()

    def test_remaining_seconds_reported(self, clock, fresh_ttl):
        lease = ControlLease()
        lease.claim("a", Tier.L1)
        lease.record_write("a")
        clock.advance(20)
        assert lease.seconds_remaining() == pytest.approx(100, abs=0.1)

    def test_query_does_not_renew(self, clock, fresh_ttl):
        lease = ControlLease()
        lease.claim("a", Tier.L1)
        lease.record_write("a")
        clock.advance(60)
        lease.snapshot()
        lease.seconds_remaining()
        assert lease.seconds_remaining() == pytest.approx(60, abs=0.1)

    def test_write_by_non_holder_is_ignored(self, clock, fresh_ttl):
        lease = ControlLease()
        lease.claim("a", Tier.L1)
        lease.record_write("a")
        clock.advance(60)
        lease.record_write("b")
        assert lease.seconds_remaining() == pytest.approx(60, abs=0.1)


class TestLeaseRelease:
    def test_holder_releases(self, clock, fresh_ttl):
        lease = ControlLease()
        lease.claim("a", Tier.L1)
        lease.record_write("a")
        assert lease.release("a") is True
        assert lease.is_free()

    def test_non_holder_cannot_release(self, clock, fresh_ttl):
        lease = ControlLease()
        lease.claim("a", Tier.L1)
        lease.record_write("a")
        assert lease.release("b") is False
        assert lease.holder == "a"

    def test_release_and_revoke_reject_active_reservation(self, clock, fresh_ttl):
        lease = ControlLease()
        reservation = lease.reserve("a", Tier.L1)
        assert lease.release("a") is False
        assert lease.revoke() is None
        assert lease.holder == "a"
        assert lease.reserve("b", Tier.L2) is None
        assert lease.commit(reservation) is True
        assert lease.revoke() == "a"
        assert lease.is_free()

    def test_release_succeeds_after_last_active_reservation_commits(self, clock, fresh_ttl):
        lease = ControlLease()
        first = lease.reserve("a", Tier.L1)
        second = lease.reserve("a", Tier.L2)
        assert lease.rollback(first) is True
        assert lease.release("a") is False
        assert lease.commit(second) is True
        assert lease.release("a") is True
        assert lease.is_free()

    def test_panel_revoke_works_on_any_holder(self, clock, fresh_ttl):
        lease = ControlLease()
        lease.claim("a", Tier.L1)
        lease.record_write("a")
        assert lease.revoke() == "a"
        assert lease.is_free()

    def test_revoke_when_free(self):
        lease = ControlLease()
        assert lease.revoke() is None
        assert lease.is_free()


class TestLeaseDecoupledFromConnection:
    def test_session_close_keeps_lease(self, clock, fresh_ttl):
        hub = SessionHub()
        lease = ControlLease(hub)
        s = hub.open("127.0.0.1:1")
        s.authenticate(Principal("mcp-bridge", Tier.L1, "AI 助手"))
        lease.claim("mcp-bridge", Tier.L1)
        lease.record_write("mcp-bridge")

        hub.close(s)
        assert lease.holder == "mcp-bridge"
        assert lease.snapshot().holder_connected is False

    def test_reconnect_same_client_recovers_holder(self, clock, fresh_ttl):
        hub = SessionHub()
        lease = ControlLease(hub)
        first = hub.open("127.0.0.1:1")
        first.authenticate(Principal("mcp-bridge", Tier.L1, "AI 助手"))
        lease.claim("mcp-bridge", Tier.L1)
        lease.record_write("mcp-bridge")
        hub.close(first)

        clock.advance(3)
        again = hub.open("127.0.0.1:2")
        again.authenticate(Principal("mcp-bridge", Tier.L1, "AI 助手"))
        assert lease.claim("mcp-bridge", Tier.L1) is True
        assert lease.snapshot().holder_connected is True

        other = hub.open("127.0.0.1:3")
        other.authenticate(Principal("stranger", Tier.L2, "stranger"))
        assert lease.claim("stranger", Tier.L2) is False

    def test_crashed_holder_gives_up_after_ttl(self, clock, fresh_ttl):
        hub = SessionHub()
        lease = ControlLease(hub)
        s = hub.open("127.0.0.1:1")
        s.authenticate(Principal("dead", Tier.L1, "dead"))
        lease.claim("dead", Tier.L1)
        lease.record_write("dead")
        hub.close(s)

        clock.advance(lease_config.ttl_seconds + 1)
        assert lease.claim("next", Tier.L1) is True


class TestLeaseSnapshot:
    def test_free_snapshot_says_no_holder(self):
        snap = ControlLease().snapshot()
        assert snap.is_held is False and snap.holder is None and snap.holder_connected is False

    def test_snapshot_carries_tier_and_idle_time(self, clock, fresh_ttl):
        lease = ControlLease()
        lease.claim("a", Tier.L2)
        lease.record_write("a")
        clock.advance(15)
        snap = lease.snapshot()
        assert snap.tier == "L2"
        assert snap.since_last_write_seconds == pytest.approx(15, abs=0.1)
        assert snap.last_written_at is not None
