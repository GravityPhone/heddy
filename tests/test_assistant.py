"""The Responses API wrapper, exercised against real SDK response objects and a fake client."""

import httpx
import openai
import pytest
from openai.types.responses import Response

from heddy.assistant.conversation import Conversation
from heddy.assistant.manager import AssistantManager
from heddy.assistant.tools import Tool, ToolRegistry
from heddy.events import ApplicationEvent, ApplicationEventType, AssistantRequest
from heddy.exceptions import AssistantError


def make_response(response_id, output, status="completed", **extra):
    return Response.model_validate(
        {
            **extra,
            "id": response_id,
            "object": "response",
            "created_at": 0,
            "model": "test-model",
            "status": status,
            "output": output,
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": [],
        }
    )


def message(text):
    return {
        "type": "message",
        "id": "msg_1",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def function_call(call_id, name, arguments):
    return {
        "type": "function_call",
        "id": f"fc_{call_id}",
        "call_id": call_id,
        "name": name,
        "arguments": arguments,
        "status": "completed",
    }


class FakeResponses:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeClient:
    def __init__(self, responses):
        self.responses = FakeResponses(responses)


def make_manager(responses, tools=None, **kwargs):
    client = FakeClient(responses)
    conversation = Conversation(timer_factory=lambda interval, fn: _NoTimer())
    manager = AssistantManager(
        client,  # type: ignore[arg-type]
        conversation=conversation,
        tools=ToolRegistry(tools or []),
        model="test-model",
        instructions="Be brief.",
        **kwargs,
    )
    return manager, client.responses


class _NoTimer:
    daemon = False

    def start(self):
        pass

    def cancel(self):
        pass


def test_plain_question_gets_a_spoken_reply():
    manager, responses = make_manager([make_response("resp_1", [message("It is noon.")])])

    reply = manager.ask(AssistantRequest(text="what time is it"))

    assert reply == "It is noon."
    call = responses.calls[0]
    assert call["model"] == "test-model"
    assert call["instructions"] == "Be brief."
    assert call["previous_response_id"] is None
    assert call["tools"] == []
    assert call["input"] == [
        {"role": "user", "content": [{"type": "input_text", "text": "what time is it"}]}
    ]
    assert manager.conversation.previous_response_id == "resp_1"


def test_follow_up_questions_chain_to_the_previous_response():
    manager, responses = make_manager(
        [make_response("resp_1", [message("Paris.")]), make_response("resp_2", [message("2.1M.")])]
    )
    manager.ask(AssistantRequest(text="capital of France?"))
    manager.ask(AssistantRequest(text="population?"))
    assert responses.calls[1]["previous_response_id"] == "resp_1"
    assert manager.conversation.previous_response_id == "resp_2"


def test_tool_calls_are_executed_and_fed_back():
    sent = []
    tool = Tool(
        name="send_text_message",
        description="Send.",
        parameters={"type": "object", "properties": {}},
        handler=lambda args: sent.append(args) or "Message sent.",
    )
    manager, responses = make_manager(
        [
            make_response(
                "resp_1", [function_call("call_1", "send_text_message", '{"message": "hi mum"}')]
            ),
            make_response("resp_2", [message("Done, I texted your mum.")]),
        ],
        tools=[tool],
    )

    reply = manager.ask(AssistantRequest(text="text my mum hi"))

    assert reply == "Done, I texted your mum."
    assert sent == [{"message": "hi mum"}]
    assert responses.calls[0]["tools"] == [tool.spec()]
    assert responses.calls[1]["previous_response_id"] == "resp_1"
    assert responses.calls[1]["input"] == [
        {"type": "function_call_output", "call_id": "call_1", "output": "Message sent."}
    ]


def test_snapshot_is_sent_as_an_image_data_url(tmp_path):
    image = tmp_path / "snap.png"
    image.write_bytes(b"\x89PNG fake")
    manager, responses = make_manager([make_response("resp_1", [message("A cat.")])])

    manager.ask(AssistantRequest(text="what is this?", image_path=image))

    content = responses.calls[0]["input"][0]["content"]
    assert content[0] == {"type": "input_text", "text": "what is this?"}
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/png;base64,iVBOR")


def test_empty_reply_is_an_error():
    manager, _ = make_manager([make_response("resp_1", [])])
    with pytest.raises(AssistantError, match="empty reply"):
        manager.ask(AssistantRequest(text="hello?"))


def test_api_errors_are_wrapped():
    manager, _ = make_manager([openai.OpenAIError("rate limited")])
    with pytest.raises(AssistantError, match="rate limited"):
        manager.ask(AssistantRequest(text="hi"))


def test_model_level_error_is_reported():
    response = make_response(
        "resp_1", [], status="failed", error={"code": "server_error", "message": "model overloaded"}
    )
    manager, _ = make_manager([response])
    with pytest.raises(AssistantError, match="model overloaded"):
        manager.ask(AssistantRequest(text="hi"))


def test_a_vanished_previous_response_starts_a_fresh_conversation():
    not_found = openai.NotFoundError(
        "Previous response not found",
        response=httpx.Response(404, request=httpx.Request("POST", "https://api.openai.com")),
        body=None,
    )
    manager, responses = make_manager(
        [
            make_response("resp_old", [message("first")]),
            not_found,
            make_response("resp_new", [message("fresh start")]),
        ]
    )
    manager.ask(AssistantRequest(text="one"))

    assert manager.ask(AssistantRequest(text="two")) == "fresh start"
    assert responses.calls[1]["previous_response_id"] == "resp_old"
    assert responses.calls[2]["previous_response_id"] is None
    assert manager.conversation.previous_response_id == "resp_new"


def test_runaway_tool_loops_are_stopped():
    calls = [make_response(f"resp_{i}", [function_call(f"c{i}", "noop", "{}")]) for i in range(3)]
    manager, _ = make_manager(calls, max_tool_rounds=1)
    with pytest.raises(AssistantError, match="calling tools"):
        manager.ask(AssistantRequest(text="loop"))


def test_handle_wraps_success_and_failure_in_the_event():
    manager, _ = make_manager(
        [make_response("resp_1", [message("ok")]), openai.OpenAIError("down")]
    )
    good = manager.handle(ApplicationEvent(ApplicationEventType.AI_INTERACT, request="plain text"))
    assert good.ok and good.result == "ok"
    bad = manager.handle(
        ApplicationEvent(ApplicationEventType.AI_INTERACT, request=AssistantRequest(text="x"))
    )
    assert not bad.ok and "down" in bad.error


def test_incomplete_responses_still_return_their_text():
    manager, _ = make_manager(
        [make_response("resp_1", [message("Partial answer")], status="incomplete")]
    )
    assert manager.ask(AssistantRequest(text="long question")) == "Partial answer"
