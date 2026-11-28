"""Waiting for the app under test, shared by the headless TUI modules."""

from textual.worker import WorkerCancelled


async def settle(app, pilot):
    """Let the workers finish and the screen redraw; a superseded worker is not a failure."""
    for _ in range(3):
        try:
            await app.workers.wait_for_complete()
        except WorkerCancelled:
            pass
        await pilot.pause()


async def until(pilot, check):
    for _ in range(200):
        if check():
            return
        await pilot.pause()
    raise AssertionError("condition never became true")
