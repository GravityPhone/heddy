from enum import Enum
from typing import Optional
import openai
import time
import threading
import requests
import json
import logging
from heddy.application_event import ApplicationEvent, ProcessingStatus
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
from heddy.vision_module import VisionModule

class AssistantResultStatus(Enum):
    SUCCESS = 1
    ERROR = -1

@dataclass
class AssitsantResult:
    text: Optional[str]
    error: Optional[str]
    status: AssistantResultStatus


class EventHandler(AssistantEventHandler):
    
    def on_text_created(self, text: str) -> None:
        print(f"\nassistant > ", end="", flush=True)

    def on_text_delta(self, delta, snapshot):
        # Access the delta attribute correctly
        if 'content' in delta:
            for content_change in delta['content']:
                if content_change['type'] == 'text':
                    print(content_change['text']['value'], end="", flush=True)
                    if 'annotations' in content_change['text']:
                        print("Annotations:", content_change['text']['annotations'])

    def on_tool_call_created(self, run):
        print("\nassistant > Processing tool call\n", flush=True)
        # Check if the run requires action and has the submit_tool_outputs type
        if run.required_action.type == 'submit_tool_outputs':
            # Iterate over each tool call in the tool_calls list
            for tool_call in run.required_action.submit_tool_outputs.tool_calls:
                # Check if the tool call is of type function and is the expected function
                if tool_call.type == 'function' and tool_call.function.name == 'textzapier':
                    # Parse the JSON string in arguments to a Python dictionary
                    arguments = json.loads(tool_call.function.arguments)
                    text_to_send = arguments['text']
                    self.send_text_via_zapier(text_to_send, tool_call.id)

    def send_text_via_zapier(self, text: str, tool_call_id: str):
        webhook_url = "https://hooks.zapier.com/hooks/catch/82343/19816978ac224264aa3eec6c8c911e10/"
        payload = {"text": text}
        try:
            response = requests.post(webhook_url, json=payload)
            if response.status_code == 200:
                logging.info("Text sent successfully via Zapier.")
                self.submit_tool_output(tool_call_id, True)
            else:
                logging.error(f"Failed to send text via Zapier. Status code: {response.status_code}, Response: {response.text}")
                self.submit_tool_output(tool_call_id, False)
        except Exception as e:
            logging.exception("Exception occurred while sending text via Zapier.")
            self.submit_tool_output(tool_call_id, False)

    def submit_tool_output(self, tool_call_id: str, success: bool):
        output_status = "Success" if success else "Failure"
        # Implement the logic to submit the tool output back to the thread run
        # This might involve calling a method from the OpenAI API client
        print(f"Tool output submitted: {output_status}")

    def on_tool_call_delta(self, delta: RequiredActionFunctionToolCall, snapshot: RequiredActionFunctionToolCall):
        if delta.type == 'code_interpreter':
            if delta.code_interpreter.input:
                print(delta.code_interpreter.input, end="", flush=True)
            if delta.code_interpreter.outputs:
                print(f"\n\noutput >", flush=True)
                for output in delta.code_interpreter.outputs:
                    if output.type == "logs":
                        print(f"\n{output.logs}", flush=True)



def tool_call_zapier(arguments):
    webhook_url = "https://hooks.zapier.com/hooks/catch/82343/19816978ac224264aa3eec6c8c911e10/"
    
    # Parse the arguments as JSON if it's a string
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    
    # Access the 'message' key instead of 'text'
    text_to_send = arguments.get('message', '')  # Default to empty string if 'message' not found
    
    payload = {"text": text_to_send}
    try:
        response = requests.post(webhook_url, json=payload)
        if response.status_code == 200:
            return "Success!"
        else:
            return f"Failed with status code: {response.status_code}"
    except Exception as e:
        return f"Exception occurred: {str(e)}"
    
def retrieve_image_description(arguments):
    # Parse the arguments as JSON if it's a string
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    
    # Access the 'message' key
    message = arguments.get('message', '')
    
    # Create an instance of VisionModule and get the stored image description
    vision_module = VisionModule()  # Assuming VisionModule is modified to not require openai_api_key during initialization
    image_description = vision_module.get_stored_image_description()  # Get the stored description
    
    # Append the image description to the message
    message += "\n\nImage Description: " + image_description
    
    # Return the updated message
    return message
    
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

    def add_message_to_thread(self, content):
        if not self.thread_id:
            print("No thread ID set. Cannot add message.")
            return

        if self.interaction_in_progress:
            print("Previous interaction still in progress. Please wait.")
            return

        try:
            message = self.client.beta.threads.messages.create(
                thread_id=self.thread_id,
                role="user",
                content=content
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




class StreamingManager:
    def __init__(self, thread_manager, eleven_labs_manager, assistant_id=None):
        self.thread_manager = thread_manager
        self.eleven_labs_manager = eleven_labs_manager
        self.assistant_id = assistant_id
        self.event_handler = None

    def set_event_handler(self, event_handler):
        self.event_handler = event_handler
    
    def handle_required_action(self, event):
        data = event.data
        action = data.required_action
        if action.type == "submit_tool_outputs":
            calls = action.submit_tool_outputs.tool_calls
            outputs = []
            for call in calls:
                func = call.function
                if func.name == "send_text_message":
                    output = tool_call_zapier(func.arguments)
                    outputs.append({
                        "output": output,
                        "tool_call_id": call.id
                    })
                elif func.name == "send_image_description":
                    output = retrieve_image_description(func.arguments)
                    outputs.append({
                        "output": output,
                        "tool_call_id": call.id
                    })
                else:
                    raise NotImplementedError(f"{func.name=}")
            
            return openai.beta.threads.runs.submit_tool_outputs_stream(
                tool_outputs=outputs,
                run_id=data.id,
                thread_id=data.thread_id
            )
        raise NotImplementedError(f"{action.type=}")
            
    
    def handle_stream(self,):
        text = ""
        streaming_manager = openai.beta.threads.runs.create_and_stream(
                thread_id=self.thread_manager.thread_id,
                assistant_id=self.assistant_id,
            )
        while True:
            with streaming_manager as stream:
                for event in stream:
                    if isinstance(event, ThreadMessageDelta) and event.data.delta.content:
                        delta = event.data.delta.content[0].text.value
                        text +=  delta if delta is not None else ""
                        continue
                    if isinstance(event, ThreadRunStepDelta):
                        continue
                    
                    print("Event received:", event)
                    if isinstance(event, ThreadRunRequiresAction):
                        streaming_manager = self.handle_required_action(event)
                        break
                    if isinstance(event, ThreadRunCompleted):
                        print("\nInteraction completed.")
                        self.thread_manager.interaction_in_progress = False
                        self.thread_manager.end_of_interaction()
                        return True, text
                        # Exit the loop once the interaction is complete
                    if isinstance(event, ThreadRunFailed):
                        print("\nInteraction failed.")
                        self.thread_manager.interaction_in_progress = False
                        self.thread_manager.end_of_interaction()
                        return False, "Generic OpenAI Error"
                        # Exit the loop if the interaction fails
                    # Add more event types as needed based on your application's requirements

    def handle_streaming_interaction(self, event: ApplicationEvent):
        if not self.assistant_id:
            print("Assistant ID is not set.")
            return
        if not self.thread_manager.thread_id:
            self.thread_manager.create_thread()
        
        content = event.request
        self.thread_manager.add_message_to_thread(content)
        success, text = self.handle_stream()

        if not success:
            event.status = ProcessingStatus.ERROR
            event.error = text
        else:
            event.status = ProcessingStatus.SUCCESS
            event.result = text
        return event
