from enum import Enum
from typing import Any, Optional
import openai
import time
import threading
import requests
import json
import logging
from heddy.application_event import ApplicationEvent, ApplicationEventType, ProcessingStatus
from heddy.state_manager import StateManager
from openai.lib.streaming import AssistantEventHandler
from openai.types.beta import Assistant, Thread
from openai.types.beta.threads import Run, RequiredActionFunctionToolCall, TextDelta
from openai.types.beta.assistant_stream_event import (
    ThreadRunRequiresAction, ThreadMessageDelta, ThreadRunCompleted,
    ThreadRunFailed, ThreadRunCancelling, ThreadRunCancelled, ThreadRunExpired, ThreadRunStepFailed,
    ThreadRunStepCancelled, ThreadRunStepDelta)
from dataclasses import dataclass
from heddy.io.sound_effects_player import AudioPlayer
from typing_extensions import override
from openai import AssistantEventHandler

class AssistantResultStatus(Enum):
    SUCCESS = 1
    ERROR = -1
    ACTION_REQUIED = 2 

class AvailableActions(Enum):
    ZAPIER=1


@dataclass
class AssitsantResult:
    status: AssistantResultStatus
    response: Optional[str] = ""
    calls: Optional[Any] = None
    error: Optional[str] = ""
    
class ThreadManager:
    def __init__(self, client):
        self.client = client
        self.thread_id = None
        self.interaction_in_progress = False
        self.reset_timer = None

    def create_thread(self):
        if self.thread_id is not None and not self.interaction_in_progress:
            print(f"Using existing thread: {self.thread_id}")
            return self.thread_id

        try:
            thread = self.client.beta.threads.create()
            self.thread_id = thread.id
            print(f"New thread created: {self.thread_id}")
            return self.thread_id
        except Exception as e:
            print(f"Failed to create a thread: {e}")
            return None

    def add_message_to_thread(self, content, snapshot_file_id=None):
        if not self.thread_id:
            print("No thread ID set. Cannot add message.")
            return

        if self.interaction_in_progress:
            print("Previous interaction still in progress. Please wait.")
            return

        try:
            message_content = [
                {
                    "type": "text",
                    "text": content  # Directly assign the content string here
                }
            ]
            attachments = []
            if snapshot_file_id:
                attachments.append({
                    "file_id": snapshot_file_id                   
                })

            message = self.client.beta.threads.messages.create(
                thread_id=self.thread_id,
                role="user",
                content=message_content,
                attachments=attachments
            )
            print(f"Message added to thread: {self.thread_id}")
        except Exception as e:
            print(f"Failed to add message to thread: {e}")

    def handle_interaction(self, content):
        if not self.thread_id or not self.interaction_in_progress:
            self.create_thread()
        self.add_message_to_thread(content)
        StateManager.last_interaction_time = time.time()  # Update the time with each interaction
        self.interaction_in_progress = True
        self.reset_last_interaction_time()

    def reset_thread(self):
        print("Resetting thread.")
        self.thread_id = None
        self.interaction_in_progress = False

    def reset_last_interaction_time(self):
        # This method resets the last interaction time and calls reset_thread after 90 seconds
        def reset():
            StateManager.last_interaction_time = None
            self.reset_thread()  # Reset the thread once the timer completes
            print("Last interaction time reset and thread reset")
            # Play the timer reset sound effect
            audio_player = AudioPlayer()
            audio_player.play_sound('timerreset.wav')  # Adjust the path as necessary
        
        # Cancel existing timer if it exists and is still running
        if self.reset_timer is not None and self.reset_timer.is_alive():
            self.reset_timer.cancel()
        
        # Create and start a new timer
        self.reset_timer = threading.Timer(90, reset)
        self.reset_timer.start()

    def end_of_interaction(self):
        # Call this method at the end of an interaction to reset the timer
        self.reset_last_interaction_time()




class EventHandler(AssistantEventHandler):
    @override
    def on_text_created(self, text) -> None:
        print(f"\nassistant > ", end="", flush=True)
      
    @override
    def on_text_delta(self, delta, snapshot):
        print(delta.value, end="", flush=True)
      
    def on_tool_call_created(self, tool_call):
        print(f"\nassistant > {tool_call.type}\n", flush=True)
  
    def on_tool_call_delta(self, delta, snapshot):
        if delta.type == 'code_interpreter':
            if delta.code_interpreter.input:
                print(delta.code_interpreter.input, end="", flush=True)
            if delta.code_interpreter.outputs:
                print(f"\n\noutput >", flush=True)
                for output in delta.code_interpreter.outputs:
                    if output.type == "logs":
                        print(f"\n{output.logs}", flush=True)

class StreamingManager:
    def __init__(self, thread_manager, eleven_labs_manager, assistant_id=None, openai_client=None):
        self.thread_manager = thread_manager
        self.eleven_labs_manager = eleven_labs_manager
        self.assistant_id = assistant_id
        self.openai_client = openai_client or openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.event_handler = None
        self.text = ""  # Initialize the text attribute

    def set_event_handler(self, event_handler):
        self.event_handler = event_handler
    
    def func_name_to_application_event(self, func):
        if func.name == "send_text_message":
            return ApplicationEventType.ZAPIER
        else:
            raise NotImplementedError(f"{func.name=}")

    def resolve_calls(self, event):
        data = event.data
        action = data.required_action
        if action.type == "submit_tool_outputs":
            _tool_calls = action.submit_tool_outputs.tool_calls
            tool_calls = []
            for call in _tool_calls:
                func = call.function
                tool_calls.append({
                    "type": self.func_name_to_application_event(func),
                    "args": func.arguments,
                    "tool_call_id": call.id
                })
            
            return {
                "tools": tool_calls,
                "run_id": data.id,
                "thread_id": data.thread_id
            }
        elif action.type == "upload_image":
            return self.upload_image_to_openai(event)
        elif action.type == "snapshot":
            return self.handle_snapshot(event)
    
    def upload_image_to_openai(self, event):
        image_path = event.image_path
        with open(image_path, "rb") as image_file:
            response = self.openai_client.files.create(
                file=image_file,
                purpose="vision"  # Ensure the purpose is set to vision
            )
        return response.id
    
    def handle_snapshot(self, event):
        self.vision_module.capture_image_async()
        self.vision_module.capture_complete.wait()
        file_id = self.upload_image_to_openai(event)
        return file_id
    
    def submit_tool_calls_and_stream(self, result):
        return openai.beta.threads.runs.submit_tool_outputs_stream(
            tool_outputs=[{
                "output": call["output"],
                "tool_call_id": call["tool_call_id"]
            } for call in result["tools"]],
            run_id=result["run_id"],
            thread_id=result["thread_id"]
        )
    
    def handle_stream(self, manager):
        for message in manager:
            if message['role'] == 'assistant':
                print(f"Triggering SYNTHESIZE event with message: {message['content']}")
                return ApplicationEvent(
                    type=ApplicationEventType.SYNTHESIZE,
                    request=message['content']
                )
    
    def handle_streaming_interaction(self, event: ApplicationEvent):
        if not self.assistant_id:
            print("Assistant ID is not set.")
            return
        if not self.thread_manager.thread_id:
            self.thread_manager.create_thread()

        print(f"Handling streaming interaction for event: {event}")

        content = [
            {
                "type": "text",
                "text": event.request.get("transcription_text")
            }
        ]

        if event.request.get("snapshot_file_id"):
            content.append({
                "type": "image_file",
                "image_file": {"file_id": event.request.get("snapshot_file_id"), "detail": "high"}
            })

        print(f"Constructed content: {content}")

        try:
            if event.type == ApplicationEventType.AI_TOOL_RETURN:
                manager = self.submit_tool_calls_and_stream(event.request)
            else:
                content = content[0]["text"]
                self.text = ""
                self.thread_manager.add_message_to_thread(content)
                
                with self.openai_client.beta.threads.runs.stream(
                    thread_id=self.thread_manager.thread_id,
                    assistant_id=self.assistant_id,
                    event_handler=EventHandler(),
                ) as stream:
                    stream.until_done()
                manager = stream  # Ensure manager is assigned

            result = self.handle_stream(manager)
            if result and result.type == ApplicationEventType.SYNTHESIZE:
                synthesized_event = self.synthesizer.synthesize(result)
                return ApplicationEvent(
                    type=ApplicationEventType.PLAY,
                    request=synthesized_event.result
                )
            return result

        except Exception as e:
            print(f"Error during streaming interaction: {e}")
            return AssitsantResult(
                error=str(e),
                status=AssistantResultStatus.ERROR
            )

