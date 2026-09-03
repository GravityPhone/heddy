import dataclasses

import pytest

from heddy.events import ApplicationEvent, ApplicationEventType, AssistantRequest, ProcessingStatus


def test_new_event_is_pending():
    event = ApplicationEvent(ApplicationEventType.LISTEN)
    assert event.status is ProcessingStatus.INIT
    assert not event.ok
    assert event.request is None and event.result is None and event.error is None


def test_succeed_records_result_and_clears_error():
    event = ApplicationEvent(ApplicationEventType.TRANSCRIBE, request="a.wav")
    event.fail("first attempt failed")
    assert event.succeed("hello") is event
    assert event.ok
    assert event.result == "hello"
    assert event.error is None


def test_fail_records_error():
    event = ApplicationEvent(ApplicationEventType.PLAY).fail("no sound card")
    assert event.status is ProcessingStatus.ERROR
    assert event.error == "no sound card"
    assert not event.ok


def test_assistant_request_is_immutable():
    request = AssistantRequest(text="hi")
    assert request.image_path is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.text = "changed"  # type: ignore[misc]
