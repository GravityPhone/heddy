"""Talks to an OpenAI model through the Responses API.

One :meth:`AssistantManager.ask` call sends the user's transcribed question
(plus a snapshot, if any), runs any tool calls the model requests, and returns
the model's final spoken reply. Conversation context is carried by
:class:`~heddy.assistant.conversation.Conversation`.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

import openai

from heddy.assistant.conversation import Conversation
from heddy.assistant.tools import ToolRegistry
from heddy.config import DEFAULT_INSTRUCTIONS, DEFAULT_MAX_OUTPUT_TOKENS, DEFAULT_MODEL
from heddy.events import ApplicationEvent, AssistantRequest
from heddy.exceptions import AssistantError

log = logging.getLogger(__name__)

_IMAGE_MIME_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


class AssistantManager:
    def __init__(
        self,
        client: openai.OpenAI,
        *,
        conversation: Conversation,
        tools: ToolRegistry | None = None,
        model: str = DEFAULT_MODEL,
        instructions: str = DEFAULT_INSTRUCTIONS,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        max_tool_rounds: int = 5,
    ) -> None:
        self._client = client
        self.conversation = conversation
        self.tools = tools or ToolRegistry()
        self.model = model
        self.instructions = instructions
        self.max_output_tokens = max_output_tokens
        self.max_tool_rounds = max_tool_rounds

    def handle(self, event: ApplicationEvent) -> ApplicationEvent:
        """Pipeline handler for ``AI_INTERACT`` events."""
        request = event.request
        if not isinstance(request, AssistantRequest):
            request = AssistantRequest(text=str(request))
        try:
            return event.succeed(self.ask(request))
        except AssistantError as exc:
            log.error("%s", exc)
            return event.fail(str(exc))

    def ask(self, request: AssistantRequest) -> str:
        """Send the request, satisfy tool calls, and return the reply text."""
        items: list[dict[str, Any]] = [self._user_message(request)]
        try:
            for _ in range(self.max_tool_rounds + 1):
                response = self._create(items)
                calls = [item for item in response.output if item.type == "function_call"]
                if not calls:
                    return self._reply_text(response)
                items = [
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": self.tools.call(call.name, call.arguments),
                    }
                    for call in calls
                ]
        except openai.OpenAIError as exc:
            raise AssistantError(f"OpenAI request failed: {exc}") from exc
        raise AssistantError("The assistant kept calling tools without answering.")

    def _create(self, items: list[dict[str, Any]]) -> openai.types.responses.Response:
        previous_id = self.conversation.previous_response_id
        try:
            response = self._request(items, previous_id)
        except openai.NotFoundError:
            if previous_id is None:
                raise
            log.warning("Previous response %s is gone; starting a new conversation", previous_id)
            self.conversation.reset()
            response = self._request(items, None)

        self.conversation.touch(response.id)
        if response.error is not None:
            raise AssistantError(f"The model returned an error: {response.error.message}")
        if response.status == "incomplete":
            reason = response.incomplete_details.reason if response.incomplete_details else "?"
            log.warning("Response %s is incomplete (%s)", response.id, reason)
        return response

    def _request(
        self, items: list[dict[str, Any]], previous_id: str | None
    ) -> openai.types.responses.Response:
        log.debug("Requesting %s (previous response: %s)", self.model, previous_id)
        return self._client.responses.create(
            model=self.model,
            instructions=self.instructions,
            input=items,
            tools=self.tools.specs(),
            previous_response_id=previous_id,
            max_output_tokens=self.max_output_tokens,
        )

    @staticmethod
    def _reply_text(response: openai.types.responses.Response) -> str:
        text = (response.output_text or "").strip()
        if not text:
            raise AssistantError("The assistant returned an empty reply.")
        return text

    @staticmethod
    def _user_message(request: AssistantRequest) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "input_text", "text": request.text}]
        if request.image_path is not None:
            content.append(
                {
                    "type": "input_image",
                    "image_url": _image_data_url(request.image_path),
                    "detail": "auto",
                }
            )
        return {"role": "user", "content": content}


def _image_data_url(path: Path) -> str:
    mime_type = _IMAGE_MIME_TYPES.get(path.suffix.lower(), "image/png")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
