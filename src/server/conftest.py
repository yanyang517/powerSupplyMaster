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