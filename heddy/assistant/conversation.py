"""Conversation continuity with an inactivity timeout.

The OpenAI Responses API keeps context by chaining each request to the
previous response id. :class:`Conversation` remembers that id and forgets it
after a period of silence, so a question asked much later starts fresh instead
of dragging in stale context. An optional callback lets the app play a sound
when the context is dropped.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from heddy.config import DEFAULT_CONVERSATION_TIMEOUT

log = logging.getLogger(__name__)

TimerFactory = Callable[[float, Callable[[], None]], threading.Timer]


class Conversation:
    def __init__(
        self,
        timeout: float = DEFAULT_CONVERSATION_TIMEOUT,
        *,
        on_reset: Callable[[], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        timer_factory: TimerFactory = threading.Timer,
    ) -> None:
        self.timeout = timeout
        self._on_reset = on_reset
        self._clock = clock
        self._timer_factory = timer_factory
        self._lock = threading.Lock()
        self._response_id: str | None = None
        self._last_activity = 0.0
        self._timer: threading.Timer | None = None

    @property
    def previous_response_id(self) -> str | None:
        """The id to chain the next request to, or ``None`` after a timeout."""
        with self._lock:
            if self._response_id is not None and self._expired():
                self._clear()
            return self._response_id

    @property
    def is_active(self) -> bool:
        return self.previous_response_id is not None

    def touch(self, response_id: str) -> None:
        """Record the latest response and restart the inactivity timer."""
        with self._lock:
            self._response_id = response_id
            self._last_activity = self._clock()
            self._arm_timer()

    def reset(self) -> None:
        """Forget the current conversation immediately (no callback)."""
        with self._lock:
            self._clear()

    def _expired(self) -> bool:
        return self._clock() - self._last_activity >= self.timeout

    def _clear(self) -> None:
        self._response_id = None
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _arm_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        timer = self._timer_factory(self.timeout, self._expire)
        timer.daemon = True
        timer.start()
        self._timer = timer

    def _expire(self) -> None:
        with self._lock:
            if self._response_id is None:
                return
            self._clear()
        log.info("Conversation timed out after %.0f seconds of silence", self.timeout)
        if self._on_reset is not None:
            self._on_reset()
