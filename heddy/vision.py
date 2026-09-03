"""Webcam capture for the "snapshot" command.

The picture is taken with ``fswebcam`` as soon as the user says the keyword, on
a background thread, so it is usually ready by the time the question has been
transcribed. It is then attached to the assistant request as an image.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
import threading
from pathlib import Path

from heddy.config import DEFAULT_CAMERA_DEVICE
from heddy.events import ApplicationEvent, AssistantRequest

log = logging.getLogger(__name__)

CAPTURE_FAILED_NOTE = "(Note: the camera snapshot failed, so no image is attached.)"


class Camera:
    """Takes still images from a V4L2 device using ``fswebcam``."""

    def __init__(
        self,
        device: str = DEFAULT_CAMERA_DEVICE,
        *,
        resolution: str = "1280x720",
        output_path: Path | str | None = None,
        capture_timeout: float = 30.0,
    ) -> None:
        self.device = device
        self.resolution = resolution
        default_path = Path(tempfile.gettempdir()) / "heddy_snapshot.png"
        self.output_path = Path(output_path) if output_path else default_path
        self._capture_timeout = capture_timeout
        self._done = threading.Event()
        self._done.set()
        self._image_path: Path | None = None

    def capture_async(self) -> None:
        """Start taking a picture on a background thread."""
        self._done.clear()
        self._image_path = None
        threading.Thread(target=self._capture, name="heddy-camera", daemon=True).start()

    def wait_for_image(self, timeout: float | None = None) -> Path | None:
        """Block until the last capture finished; ``None`` if it failed or timed out."""
        finished = self._done.wait(timeout if timeout is not None else self._capture_timeout + 5)
        if not finished:
            log.error("Timed out waiting for the camera")
            return None
        return self._image_path

    def attach_snapshot(self, event: ApplicationEvent) -> ApplicationEvent:
        """Pipeline handler for ``GET_SNAPSHOT``: pair the transcript with the image.

        If the capture failed the request is still sent, with a note so the
        assistant can tell the user what happened.
        """
        text = str(event.request)
        image_path = self.wait_for_image()
        if image_path is None:
            log.warning("No snapshot available; sending the question without an image")
            return event.succeed(AssistantRequest(text=f"{text}\n\n{CAPTURE_FAILED_NOTE}"))
        return event.succeed(AssistantRequest(text=text, image_path=image_path))

    def _capture(self) -> None:
        command = [
            "fswebcam",
            "--no-banner",
            "--device",
            self.device,
            "--resolution",
            self.resolution,
            "--png",
            "1",
            "--save",
            str(self.output_path),
        ]
        try:
            self.output_path.unlink(missing_ok=True)
            log.info("Taking a picture with %s", self.device)
            subprocess.run(
                command, check=True, capture_output=True, text=True, timeout=self._capture_timeout
            )
            if self.output_path.is_file():
                self._image_path = self.output_path
                log.info("Snapshot saved to %s", self.output_path)
            else:
                log.error("fswebcam finished but produced no file")
        except FileNotFoundError:
            log.error("fswebcam is not installed; install it to use snapshots")
        except subprocess.CalledProcessError as exc:
            log.error("fswebcam failed: %s", (exc.stderr or "").strip() or exc)
        except subprocess.TimeoutExpired:
            log.error("fswebcam timed out after %.0f seconds", self._capture_timeout)
        finally:
            self._done.set()
