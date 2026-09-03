"""Silence the warnings PortAudio and ALSA print while probing devices."""

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def suppress_stderr() -> Iterator[None]:
    """Temporarily point file descriptor 2 at ``/dev/null``.

    The ALSA and JACK back-ends write their "unable to open slave" style
    warnings straight to the C-level stderr, so replacing ``sys.stderr`` alone
    does nothing. Redirecting the descriptor itself keeps start-up output clean.
    """
    sys.stderr.flush()
    saved_fd = os.dup(2)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull_fd, 2)
        yield
    finally:
        os.dup2(saved_fd, 2)
        os.close(devnull_fd)
        os.close(saved_fd)
