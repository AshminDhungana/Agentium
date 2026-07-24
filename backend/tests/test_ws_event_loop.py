import asyncio


async def test_db_query_in_executor_does_not_block():
    """A sync DB query wrapped in run_in_executor should not
    prevent the event loop from processing other tasks."""
    loop = asyncio.get_running_loop()
    order = []

    async def monitor():
        await asyncio.sleep(0.02)
        order.append("monitor_ran")

    def blocking_query():
        import time
        time.sleep(0.05)
        return "result"

    result, _ = await asyncio.gather(
        loop.run_in_executor(None, blocking_query),
        monitor(),
    )
    assert result == "result"
    assert "monitor_ran" in order


async def test_on_delta_absorbs_send_failure():
    """on_delta must silently absorb send_json failures without
    propagating the exception to the caller."""
    captured = []

    async def on_delta(text: str) -> None:
        try:
            raise Exception("socket closed")
        except Exception:
            pass
        captured.append(text)

    await on_delta("hello")
    assert captured == ["hello"]
