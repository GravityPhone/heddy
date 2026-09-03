from pathlib import Path

import pytest

from heddy.controller import DEFAULT_GREETING, MainController
from heddy.events import ApplicationEvent, ApplicationEventType, AssistantRequest
from heddy.exceptions import RecordingError
from heddy.resources import (
    LISTENING_SOUND,
    RESPOND_SOUND,
    SNAPSHOT_SOUND,
    START_RECORDING_SOUND,
)

T = ApplicationEventType


def run_steps(controller: MainController, event: ApplicationEvent, limit: int = 50) -> list[T]:
    """Drive the controller until its script of keywords runs out; return the event trail."""
    trail = [event.type]
    try:
        for _ in range(limit):
            event = controller.step(event)
            trail.append(event.type)
    except KeyboardInterrupt:
        pass
    return trail


def test_start_plays_the_listening_sound_and_greets(fakes):
    controller = fakes.controller()
    event = controller.step(ApplicationEvent(T.START))
    assert event.type is T.SYNTHESIZE
    assert event.request == DEFAULT_GREETING
    assert fakes.player.sounds == [LISTENING_SOUND]


def test_text_interaction_end_to_end(fakes):
    fakes.detector.words = ["computer", "reply"]
    controller = fakes.controller()

    trail = run_steps(controller, ApplicationEvent(T.START))

    assert trail == [
        T.START,
        T.SYNTHESIZE,
        T.PLAY,
        T.LISTEN,
        T.START_RECORDING,
        T.LISTEN,
        T.STOP_RECORDING,
        T.TRANSCRIBE,
        T.AI_INTERACT,
        T.SYNTHESIZE,
        T.PLAY,
        T.LISTEN,
    ]
    assert fakes.recorder.starts == 1 and fakes.recorder.stops == 1
    assert fakes.transcriber.requests == [fakes.recorder.path]
    assert fakes.assistant.requests == [AssistantRequest(text="what time is it")]
    assert fakes.synthesizer.texts == [DEFAULT_GREETING, "It is noon."]
    assert len(fakes.player.played) == 2
    assert fakes.detector.cleared == 1, "the detector is muted while the reply is spoken"
    assert fakes.player.sounds == [LISTENING_SOUND, START_RECORDING_SOUND, RESPOND_SOUND]
    assert not controller.is_recording and not controller.picture_mode


def test_snapshot_interaction_attaches_the_image(fakes):
    fakes.detector.words = ["computer", "snapshot", "reply"]
    controller = fakes.controller()

    trail = run_steps(controller, ApplicationEvent(T.LISTEN))

    assert T.USE_SNAPSHOT in trail and T.GET_SNAPSHOT in trail
    assert fakes.camera.captures == 1
    assert fakes.assistant.requests == [
        AssistantRequest(text="what time is it", image_path=fakes.camera.image_path)
    ]
    assert fakes.player.sounds == [START_RECORDING_SOUND, SNAPSHOT_SOUND, RESPOND_SOUND]
    assert not controller.picture_mode


@pytest.mark.parametrize(
    ("word", "recording", "picture_mode", "expected"),
    [
        ("computer", False, False, T.START_RECORDING),
        ("Computer ", False, False, T.START_RECORDING),
        ("computer", True, False, T.LISTEN),
        ("snapshot", False, False, T.LISTEN),
        ("snapshot", True, False, T.USE_SNAPSHOT),
        ("snapshot", True, True, T.LISTEN),
        ("reply", False, False, T.LISTEN),
        ("reply", True, False, T.STOP_RECORDING),
        ("reply", True, True, T.STOP_RECORDING),
        ("banana", True, False, T.LISTEN),
    ],
)
def test_keyword_rules(fakes, word, recording, picture_mode, expected):
    controller = fakes.controller()
    controller.is_recording = recording
    controller.picture_mode = picture_mode
    assert controller.handle_keyword(word).type is expected


def test_a_failed_stage_returns_to_listening(fakes):
    fakes.transcriber.error = "AssemblyAI is down"
    controller = fakes.controller()
    controller.picture_mode = True

    event = controller.step(ApplicationEvent(T.TRANSCRIBE, request=Path("x.wav")))

    assert event.type is T.LISTEN
    assert not controller.picture_mode
    assert fakes.detector.cleared == 1
    assert fakes.assistant.requests == []


def test_a_handler_exception_is_recovered(fakes):
    fakes.recorder.stop_error = RecordingError("microphone unplugged")
    controller = fakes.controller()
    controller.step(ApplicationEvent(T.START_RECORDING))
    assert controller.is_recording

    event = controller.step(ApplicationEvent(T.STOP_RECORDING))

    assert event.type is T.LISTEN
    assert not controller.is_recording


def test_failed_playback_still_returns_to_listening(fakes):
    fakes.player.error = "device busy"
    controller = fakes.controller()
    event = controller.step(ApplicationEvent(T.PLAY, request=b""))
    assert event.type is T.LISTEN


def test_unknown_event_type_is_a_programming_error(fakes):
    controller = fakes.controller()
    with pytest.raises(ValueError):
        controller.process_event(ApplicationEvent(T.EXIT))
    with pytest.raises(ValueError):
        controller.process_result(ApplicationEvent(T.EXIT).succeed())


def test_run_stops_on_exit_and_closes_the_player(fakes):
    controller = fakes.controller()
    controller.run(ApplicationEvent(T.EXIT))
    assert fakes.player.closed


def test_run_shuts_down_cleanly_on_ctrl_c_while_recording(fakes):
    fakes.detector.words = ["computer"]  # then KeyboardInterrupt from the fake detector
    controller = fakes.controller()
    controller.run(ApplicationEvent(T.LISTEN))
    assert fakes.recorder.starts == 1
    assert fakes.recorder.stops == 1, "an in-progress recording is stopped on shutdown"
    assert fakes.player.closed
