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
import uuid

class AssistantResultStatus(Enum):
    SUCCESS = 1
    ERROR = -1
    ACTION_REQUIED = 2 

class AvailableActions(Enum):
    ZAPIER=1


@dataclass
class AssistantResult:
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
            self.interaction_in_progress = True  # Set to True when starting interaction
            message_content = [
                {
                    "type": "text",
                    "text": content  # Directly assign the content string here
                }
            ]
            if snapshot_file_id:
                message_content.append({
                    "type": "image_file",
                    "image_file": {"file_id": snapshot_file_id}
                })

            message = self.client.beta.threads.messages.create(
                thread_id=self.thread_id,
                role="user",
                content=message_content
            )
            print(f"Message added to thread: {self.thread_id}")
            self.interaction_in_progress = False  # Set to False when interaction ends
        except Exception as e:
            print(f"Failed to add message to thread: {e}")
            self.interaction_in_progress = False  # Ensure it is reset on failure

    def handle_interaction(self, content):
        if not self.thread_id or not self.interaction_in_progress:
            self.create_thread()
        self.add_message_to_thread(content)
        self.interaction_in_progress = True  # Set to True when starting interaction
        StateManager.last_interaction_time = time.time()  # Update the time with each interaction
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
        self.interaction_in_progress = False  # Set to False when interaction ends
        self.reset_last_interaction_time()




class EventHandler(AssistantEventHandler):
    def __init__(self, streaming_manager):
        super().__init__()  # Ensure the base class is properly initialized
        self.streaming_manager = streaming_manager
        self.id = uuid.uuid4()  # Add a unique identifier
        print(f"EventHandler initialized with StreamingManager: {self.streaming_manager} and ID: {self.id}")

    def reset(self):
        self.streaming_manager.response_text = ""  # Reset the response_text attribute
        self.streaming_manager = None
        self.id = uuid.uuid4()  # Generate a new unique identifier
        print(f"EventHandler reset with new ID: {self.id} and StreamingManager: {self.streaming_manager}")

    @override
    def on_text_created(self, text) -> None:
        print(f"\nassistant > ", end="", flush=True)
        self.streaming_manager.response_text += text.value  # Access the string value

    @override
    def on_text_delta(self, delta, snapshot):
        print(delta.value, end="", flush=True)
        self.streaming_manager.response_text += delta.value  # Access the string value

    @override
    def on_tool_call_created(self, tool_call):
        print(f"\nassistant > {tool_call.type}\n", flush=True)

    @override
    def on_tool_call_delta(self, delta, snapshot):
        if delta.type == 'code_interpreter':
            if delta.code_interpreter.input:
                print(delta.code_interpreter.input, end="", flush=True)
                self.streaming_manager.response_text += delta.code_interpreter.input  # Append the input to the response text
            if delta.code_interpreter.outputs:
                print(f"\n\noutput >", flush=True)
                for output in delta.code_interpreter.outputs:
                    if output.type == "logs":
                        print(f"\n{output.logs}", flush=True)
                        self.streaming_manager.response_text += output.logs  # Append the logs to the response text

    @override
    def on_event(self, event):
        # Retrieve events that are denoted with 'requires_action'
        # since these will have our tool_calls
        if event.event == 'thread.run.requires_action':
            run_id = event.data.id  # Retrieve the run ID from the event data
            print(f"Calling handle_requires_action with data: {event.data} and run_id: {run_id}")
            self.handle_requires_action(event.data, run_id)

    def handle_requires_action(self, data, run_id):
        print(f"Handling requires_action with data: {data} and run_id: {run_id}")
        tool_outputs = []

        for tool in data.required_action.submit_tool_outputs.tool_calls:
            if tool.function.name == "send_text_message":
                arguments = tool.function.arguments
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                message = arguments.get("message", "")
                print(f"Sending text message with arguments: {arguments}")
                send_result = send_text_message({"message": message})
                print(f"Send result: {send_result}")
                tool_outputs.append({"tool_call_id": tool.id, "output": send_result})

        print(f"Submitting tool outputs: {tool_outputs}")
        self.submit_tool_outputs(tool_outputs, run_id)

    def submit_tool_outputs(self, tool_outputs, run_id):
        print(f"Preparing to submit tool outputs stream with run_id: {run_id}")
        with self.streaming_manager.openai_client.beta.threads.runs.submit_tool_outputs_stream(
            thread_id=self.streaming_manager.thread_manager.thread_id,
            run_id=run_id,
            tool_outputs=tool_outputs,
            event_handler=self,
        ) as stream:
            print("Starting tool outputs stream")
            for text in stream.text_deltas:
                self.streaming_manager.response_text += text
                print(f"Appending to response_text: {text}")
                print(text, end="", flush=True)
            print()

class StreamingManager:
    def __init__(self, thread_manager, eleven_labs_manager, assistant_id=None, openai_client=None):
        self.thread_manager = thread_manager
        self.eleven_labs_manager = eleven_labs_manager
        self.assistant_id = assistant_id
        self.openai_client = openai_client or openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.event_handler = EventHandler(self)  # Initialize the EventHandler instance
        self.text = ""  # Initialize the text attribute
        self.response_text = ""  # Initialize the response_text attribute

    def set_event_handler(self, event_handler):
        self.event_handler = event_handler
    
    def func_name_to_application_event(self, func):
        if func.name == "send_text_message":
            return ApplicationEventType.ZAPIER
        else:
            raise NotImplementedError(f"{func.name=}")

    def resolve_calls(self, event: ApplicationEvent):
        data = event.data
        if not isinstance(data, dict):
            raise ValueError("Event data is not a dictionary")
        action = data.get('required_action')
        if not action:
            if 'required_action' not in data:
                raise ValueError("Missing 'required_action' key in event data")
            else:
                raise ValueError("'required_action' is explicitly set to null in event data")
        if action.type == "submit_tool_outputs":
            tool_calls = action.submit_tool_outputs['tool_calls']
            results = []
            for call in tool_calls:
                if call['function']['name'] == "send_text_message":
                    print(f"Calling send_text_message with arguments: {call['function']['arguments']}")
                    result = send_text_message(call['function']['arguments'])
                    print(f"Result from send_text_message: {result}")
                    results.append({"tool_call_id": call['id'], "output": result})
            self.client.beta.threads.runs.submit_tool_outputs(
                run_id=data['id'],
                tool_outputs=results
            )
        elif action.type == "upload_image":
            return self.upload_image_to_openai(event)
        elif action.type == "snapshot":
            return self.handle_snapshot(event)
        else:
            raise ValueError("Unsupported action type")
    
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
        return self.openai_client.beta.threads.runs.submit_tool_outputs_stream(
            tool_outputs=[{
                "output": call["output"],
                "tool_call_id": call["tool_call_id"]
            } for call in result["tools"]],
            run_id=result["run_id"],
            thread_id=result["thread_id"]
        )
    
    def handle_stream(self, manager):
        response_content = ""
        try:
            for message in manager:
                print(f"Received message: {message}")
                if message['role'] == 'assistant':
                    response_content += message['content']
                    print(f"Appending message content: {message['content']}")
            if response_content:
                print(f"Triggering SYNTHESIZE event with message: {response_content}")
                return response_content  # Return the response content directly
            else:
                print("No content received from stream.")
                return None
        except Exception as e:
            print(f"Stream processing error: {str(e)}")
            return None
    
    def handle_streaming_interaction(self, event: ApplicationEvent) -> ApplicationEvent:
        print("Entering try block for streaming interaction")
        if not self.assistant_id:
            print("Assistant ID is not set.")
            return ApplicationEvent(
                type=ApplicationEventType.ERROR,
                request="Assistant ID is not set.",
                data=None
            )
        if not self.thread_manager.thread_id:
            self.thread_manager.create_thread()

        content = self.construct_content(event)
        print(f"Constructed content: {content}")

        try:
            self.response_text = ""  # Reset the response text at the beginning of the interaction
            print("Response text reset")
            self.event_handler = EventHandler(self)  # Create a new EventHandler instance
            print(f"Created new EventHandler instance with ID: {self.event_handler.id}")
            with self.openai_client.beta.threads.runs.stream(
                thread_id=self.thread_manager.thread_id,
                assistant_id=self.assistant_id,
                event_handler=EventHandler(self),  # Create a new EventHandler instance
            ) as stream:
                stream.until_done()
            print("Stream completed")
            response_text = self.response_text  # Use the stored response text

            print(f"Response text: {response_text}")

            if not event.data:
                print("Event data is None, initializing to empty dictionary.")
                event.data = {}
            print(f"Event data after initialization: {event.data}")
            if 'required_action' not in event.data:
                event.data['required_action'] = {"submit_tool_outputs": {"tool_calls": []}}
            elif event.data['required_action'] is None:
                raise ValueError("'required_action' is explicitly set to null in event data")

            # Check if the response requires a function call
            if isinstance(response_text, str):
                try:
                    response_text = json.loads(response_text)
                except json.JSONDecodeError:
                    print(f"Result is not a valid JSON: {response_text}")
                    return ApplicationEvent(
                        type=ApplicationEventType.ERROR,
                        request="Invalid response format",
                        data=None
                    )

            print(f"Parsed response_text: {response_text}")

            if "function_call" in response_text:
                function_call = response_text["function_call"]
                print(f"Function call detected: {function_call}")
                if function_call["name"] == "send_text_message":
                    parameters = function_call["parameters"]
                    if isinstance(parameters, str):
                        parameters = json.loads(parameters)
                    print(f"Function call parameters: {parameters}")
                    zapier_response = send_text_message(parameters)
                    if zapier_response == "Success!":
                        run_id = self.thread_manager.run_id
                        tool_outputs = [{
                            "tool_call_id": function_call["id"],
                            "output": zapier_response
                        }]
                        with self.openai_client.beta.threads.runs.submit_tool_outputs_stream(
                            thread_id=self.thread_manager.thread_id,
                            run_id=run_id,
                            tool_outputs=tool_outputs,
                            event_handler=self.event_handler,  # Use the reset EventHandler instance
                        ) as stream:
                            for text in stream.text_deltas:
                                self.streaming_manager.response_text += text
                                print(f"Appending to response_text: {text}")
                                print(text, end="", flush=True)
                            print()
                        response_text = self.response_text

                        return ApplicationEvent(
                            type=ApplicationEventType.SYNTHESIZE,
                            request=response_text
                        )
                    else:
                        return ApplicationEvent(
                            type=ApplicationEventType.ERROR,
                            request=zapier_response
                        )
            else:
                # Handle normal response
                return ApplicationEvent(
                    type=ApplicationEventType.SYNTHESIZE,
                    request=response_text
                )
        except Exception as e:
            print(f"Error during streaming interaction: {str(e)}...")
            return ApplicationEvent(
                type=ApplicationEventType.ERROR,
                request=str(e)[:100]
            )

    def construct_content(self, event):
        request = event.request if isinstance(event.request, dict) else {}
        content = [
            {
                "type": "text",
                "text": str(request.get("transcription_text", ""))  # Ensure the text is a string
            }
        ]

        if request.get("snapshot_file_id"):
            content.append({
                "type": "image_file",
                "image_file": {"file_id": request.get("snapshot_file_id"), "detail": "high"}
            })

        print(f"Constructed content: {content}")
        return content

def send_text_message(arguments):
    webhook_url = "https://hooks.zapier.com/hooks/catch/82343/19816978ac224264aa3eec6c8c911e10/"
    
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    
    text_to_send = arguments.get('message', '')
    payload = {"text": text_to_send}
    print(f"Sending text message via Zapier with arguments: {arguments}")
    
    response = requests.post(webhook_url, json=payload)
    print(f"Response from Zapier: {response.status_code}, {response.text}")
    
    if response.status_code == 200:
        return "Success!"
    else:
        return f"Failed with status code {response.status_code}"
















