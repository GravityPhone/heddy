import subprocess

import pytest

import heddy.vision as vision_module
from heddy.events import ApplicationEvent, ApplicationEventType, AssistantRequest
from heddy.vision import CAPTURE_FAILED_NOTE, Camera


@pytest.fixture
def snapshot_path(tmp_path):
    return tmp_path / "snap.png"


def fake_run_factory(calls, behaviour="ok"):
    def fake_run(command, **kwargs):
        calls.append(command)
        if behaviour == "missing":
            raise FileNotFoundError("fswebcam")
        if behaviour == "error":
            raise subprocess.CalledProcessError(1, command, stderr="No such device")
        if behaviour == "ok":
            save_index = command.index("--save") + 1
            with open(command[save_index], "wb") as handle:
                handle.write(b"\x89PNG")
        return subprocess.CompletedProcess(command, 0)

    return fake_run


def test_capture_produces_an_image_and_attaches_it(monkeypatch, snapshot_path):
    calls = []
    monkeypatch.setattr(vision_module.subprocess, "run", fake_run_factory(calls))
    camera = Camera("/dev/video3", output_path=snapshot_path)

    camera.capture_async()
    event = camera.attach_snapshot(
        ApplicationEvent(ApplicationEventType.GET_SNAPSHOT, request="what is this")
    )

    assert event.ok
    assert event.result == AssistantRequest(text="what is this", image_path=snapshot_path)
    assert calls[0][0] == "fswebcam"
    assert "/dev/video3" in calls[0]
    assert snapshot_path.read_bytes() == b"\x89PNG"


@pytest.mark.parametrize("behaviour", ["missing", "error", "nofile"])
def test_capture_failures_fall_back_to_text_only(monkeypatch, snapshot_path, behaviour):
    monkeypatch.setattr(vision_module.subprocess, "run", fake_run_factory([], behaviour))
    camera = Camera(output_path=snapshot_path)

    camera.capture_async()
    event = camera.attach_snapshot(
        ApplicationEvent(ApplicationEventType.GET_SNAPSHOT, request="what is this")
    )

    assert event.ok
    assert event.result.image_path is None
    assert event.result.text.startswith("what is this")
    assert CAPTURE_FAILED_NOTE in event.result.text


def test_wait_without_capture_returns_nothing(snapshot_path):
    assert Camera(output_path=snapshot_path).wait_for_image(timeout=0.01) is None


def test_stale_snapshot_is_removed_before_capturing(monkeypatch, snapshot_path):
    snapshot_path.write_bytes(b"old")
    monkeypatch.setattr(vision_module.subprocess, "run", fake_run_factory([], "error"))
    camera = Camera(output_path=snapshot_path)
    camera.capture_async()
    assert camera.wait_for_image() is None
    assert not snapshot_path.exists()
