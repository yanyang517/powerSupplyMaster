import asyncio
import pytest


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy"""
    import sys
    if sys.platform == "win32":
        # Windows requires ProactorEventLoop for asyncio
        return asyncio.WindowsProactorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session", autouse=True)
def event_loop(event_loop_policy):
    """Create an instance of the default event loop for each test session."""
    loop = event_loop_policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def isolated_access_state():
    """会话表与控制权是进程级单例，用例之间必须归零，否则租约跨用例泄漏。"""
    from . import session as session_mod
    from .session import lease as shared_lease

    shared_lease.revoke()
    for s in list(session_mod.hub):
        session_mod.hub.close(s)
    yield
    shared_lease.revoke()