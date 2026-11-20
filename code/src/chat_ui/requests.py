"""A bounded, cancellable local wait, independent of Streamlit's script runner."""

import asyncio
from collections.abc import Callable, Coroutine
from concurrent.futures import Future
from threading import Event, Thread
from time import monotonic
from typing import Any

from schema import ChatMessage


class ResponseWait:
    """The worker never reads or writes session state. Only the UI accepts its result."""

    def __init__(
        self, receive: Callable[[], Coroutine[Any, Any, ChatMessage]], timeout: float
    ) -> None:
        self.result: Future[ChatMessage] = Future()
        self.started = monotonic()
        self.timeout = timeout
        self._cancelled = Event()
        self._loop = None
        self._task = None
        self._thread = Thread(target=self._run, args=(receive,), daemon=True)
        self._thread.start()

    @property
    def elapsed(self) -> float:
        return monotonic() - self.started

    def cancel(self) -> None:
        self._cancelled.set()
        if self._loop is not None and self._task is not None:
            try:
                self._loop.call_soon_threadsafe(self._task.cancel)
            except RuntimeError:
                pass  # The loop already closed after delivering its result.

    def _run(self, receive) -> None:
        async def bounded():
            self._loop = asyncio.get_running_loop()
            self._task = asyncio.current_task()
            if self._cancelled.is_set():
                raise asyncio.CancelledError
            async with asyncio.timeout(self.timeout):
                response = await receive()
            # A transport may suppress cancellation. Its late result still exceeds our limit.
            if self.elapsed >= self.timeout:
                raise TimeoutError
            return response

        try:
            self.result.set_result(asyncio.run(bounded()))
        except asyncio.CancelledError:
            self.result.cancel()
        except Exception as error:
            self.result.set_exception(error)
