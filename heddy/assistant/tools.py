"""Function tools the assistant may call.

A :class:`Tool` pairs the JSON schema sent to the model with the Python
callable that runs when the model invokes it. Handlers return a short string
that is fed back to the model as the tool result; they never raise, so a
broken integration turns into an explanation the assistant can relay to the
user instead of a crash.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import requests

log = logging.getLogger(__name__)

ToolHandler = Callable[[dict[str, Any]], str]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def spec(self) -> dict[str, Any]:
        """The tool definition in the shape the Responses API expects."""
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "strict": True,
        }


class ToolRegistry:
    """Looks tools up by name and runs them safely."""

    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def specs(self) -> list[dict[str, Any]]:
        return [tool.spec() for tool in self._tools.values()]

    def call(self, name: str, arguments: str | None) -> str:
        """Run the named tool with JSON-encoded arguments and return its result text."""
        tool = self._tools.get(name)
        if tool is None:
            log.warning("Assistant requested unknown tool %r", name)
            return f"Error: there is no tool called {name!r}."
        try:
            parsed = json.loads(arguments or "{}")
        except ValueError:
            return "Error: the tool arguments were not valid JSON."
        if not isinstance(parsed, dict):
            return "Error: the tool arguments must be a JSON object."
        log.info("Running tool %s with %s", name, parsed)
        try:
            return tool.handler(parsed)
        except Exception as exc:  # a tool bug must not take the assistant down
            log.exception("Tool %s raised", name)
            return f"Error: the {name} tool failed: {exc}"


class ZapierWebhook:
    """Posts a text message to a Zapier "Catch Hook" trigger.

    The Zap on the other end decides what to do with it, for example send an
    SMS. The webhook URL is a secret: anyone who has it can fire the Zap.
    """

    def __init__(
        self, url: str, *, timeout: float = 10.0, session: requests.Session | None = None
    ) -> None:
        self._url = url
        self._timeout = timeout
        self._session = session or requests.Session()

    def send(self, message: str) -> str:
        message = message.strip()
        if not message:
            return "Error: no message text was provided."
        try:
            response = self._session.post(self._url, json={"text": message}, timeout=self._timeout)
        except requests.RequestException as exc:
            return f"Error: could not reach Zapier ({exc})."
        if response.status_code != 200:
            return f"Error: Zapier responded with HTTP {response.status_code}."
        return "Message sent."


def send_text_message_tool(webhook: ZapierWebhook) -> Tool:
    return Tool(
        name="send_text_message",
        description=(
            "Send a text message on the user's behalf. Use it only when the user "
            "explicitly asks to send, text, or message someone."
        ),
        parameters={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The full text of the message to send.",
                }
            },
            "required": ["message"],
            "additionalProperties": False,
        },
        handler=lambda arguments: webhook.send(str(arguments.get("message", ""))),
    )
