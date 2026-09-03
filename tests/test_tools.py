import requests

from heddy.assistant.tools import Tool, ToolRegistry, ZapierWebhook, send_text_message_tool


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class FakeSession:
    def __init__(self, status_code=200, error=None):
        self.status_code = status_code
        self.error = error
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return FakeResponse(self.status_code)


def echo_tool(name="echo"):
    return Tool(
        name=name,
        description="Echoes.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        handler=lambda args: f"echo:{args}",
    )


def test_tool_spec_is_a_strict_function_definition():
    spec = echo_tool().spec()
    assert spec["type"] == "function"
    assert spec["name"] == "echo"
    assert spec["strict"] is True
    assert spec["parameters"]["type"] == "object"


def test_registry_lists_and_calls_tools():
    registry = ToolRegistry([echo_tool()])
    assert len(registry) == 1 and "echo" in registry and registry.names == ["echo"]
    assert registry.specs() == [echo_tool().spec()]
    assert registry.call("echo", '{"a": 1}') == "echo:{'a': 1}"
    assert registry.call("echo", None) == "echo:{}"


def test_registry_reports_problems_as_text_instead_of_raising():
    def broken(args):
        raise RuntimeError("kaboom")

    registry = ToolRegistry([Tool("broken", "Breaks.", {"type": "object"}, broken)])
    assert "no tool called 'nope'" in registry.call("nope", "{}")
    assert "not valid JSON" in registry.call("broken", "{not json")
    assert "must be a JSON object" in registry.call("broken", "[1, 2]")
    assert "kaboom" in registry.call("broken", "{}")


def test_zapier_posts_the_message_text():
    session = FakeSession()
    webhook = ZapierWebhook("https://hooks.zapier.com/hooks/catch/1/x/", session=session)
    assert webhook.send("  On my way!  ") == "Message sent."
    url, kwargs = session.calls[0]
    assert url == "https://hooks.zapier.com/hooks/catch/1/x/"
    assert kwargs["json"] == {"text": "On my way!"}
    assert kwargs["timeout"] == 10.0


def test_zapier_failures_become_error_strings():
    assert "no message" in ZapierWebhook("u", session=FakeSession()).send("   ")
    assert "HTTP 500" in ZapierWebhook("u", session=FakeSession(500)).send("hi")
    offline = FakeSession(error=requests.ConnectionError("offline"))
    assert "could not reach Zapier" in ZapierWebhook("u", session=offline).send("hi")


def test_send_text_message_tool_wires_the_webhook():
    session = FakeSession()
    tool = send_text_message_tool(ZapierWebhook("u", session=session))
    assert tool.name == "send_text_message"
    assert tool.parameters["required"] == ["message"]
    assert tool.parameters["additionalProperties"] is False
    assert ToolRegistry([tool]).call("send_text_message", '{"message": "hello"}') == "Message sent."
    assert session.calls[0][1]["json"] == {"text": "hello"}
