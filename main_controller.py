import os
import time
import re
from word_detector import setup_keyword_detection, set_message_handler
from audio_recorder import start_recording, stop_recording
from assemblyai_transcriber import AssemblyAITranscriber
from assistant_manager import AssistantManager
from eleven_labs_manager import ElevenLabsManager
from vision_module import VisionModule
import openai
from openai import AssistantEventHandler
from sound_effects_player import SoundEffectsPlayer

# Initialize OpenAI client
openai.api_key = os.getenv("OPENAI_API_KEY")
openai_client = openai # This line initializes openai_client with the openai library itself

# Initialize modules with provided API keys
assemblyai_transcriber = AssemblyAITranscriber(api_key=os.getenv("ASSEMBLYAI_API_KEY"))
# Adjusted to use the hardcoded Assistant ID
eleven_labs_manager = ElevenLabsManager(api_key=os.getenv("ELEVENLABS_API_KEY"))
vision_module = VisionModule(openai_api_key=os.getenv("OPENAI_API_KEY"))

# State variables
is_recording = False
picture_mode = False
last_thread_id = None
last_interaction_time = None

# Global variable to hold the concatenated text
concatenated_text = ""

# Global set to track processed message IDs
processed_messages = set()

# Instantiate SoundEffectsPlayer
sound_effects_player = SoundEffectsPlayer()

def handle_detected_words(words):
    global is_recording, picture_mode, last_thread_id, last_interaction_time
    detected_phrase = ' '.join(words).lower().strip()
    print(f"Detected phrase: {detected_phrase}")

    if "computer" in detected_phrase and not is_recording:
        start_recording()
        is_recording = True
        print("Recording started...")
        sound_effects_player.play_sound('startrecording.wav')
    elif "snapshot" in detected_phrase and is_recording:
        picture_mode = True
        print("Picture mode activated...")
        sound_effects_player.play_sound('tricorder.wav')
    elif "reply" in detected_phrase and is_recording:
        stop_recording()
        is_recording = False
        print("Recording stopped. Processing...")
        process_recording()
        sound_effects_player.play_sound('respond.wav')  # Play when processing a reply
    else:
        # This else block can be used for any other detected phrases where you want to play a sound
        sound_effects_player.play_sound('listening.wav')  # Play for general listening or other commands

def process_recording():
    global picture_mode, last_thread_id, last_interaction_time
    transcription = assemblyai_transcriber.transcribe_audio_file("recorded_audio.wav")
    print(f"Transcription result: '{transcription}'")

    if picture_mode:
        vision_module.capture_image_async()
        description = vision_module.describe_captured_image(transcription=transcription)
        # Handle the image description through streaming interaction
        interact_with_assistant(description)
        picture_mode = False
    else:
        # Handle the transcription through streaming interaction
        interact_with_assistant(transcription)

class CustomAssistantEventHandler(AssistantEventHandler):
    def __init__(self, eleven_labs_manager):
        self.eleven_labs_manager = eleven_labs_manager
        self.complete_response = ""  # Initialize an empty string to accumulate the response

    def on_text_created(self, text) -> None:
        # This method might still be useful if you receive complete text responses directly.
        self.complete_response += text  # Append the text to the complete response
        self.play_response()

    def on_text_delta(self, delta, snapshot):
        # Check if 'delta' contains 'content' changes
        if 'content' in delta:  # Corrected access
            # Iterate through each content change
            for content_change in delta['content']:  # Corrected access
                # Check if the content change is of type 'text'
                if content_change['type'] == 'text':
                    # Extract the text value
                    text_value = content_change['text']['value']
                    # Print the text value
                    print(text_value, end="", flush=True)
                    # Concatenate the text value to the global variable
                    global concatenated_text
                    concatenated_text += text_value

    def play_response(self):
        # Check if the complete response is not empty
        if self.complete_response.strip():
            # Use ElevenLabsManager to play back the text.
            print(f"Playing message: {self.complete_response}")  # Print statement before playing
            self.eleven_labs_manager.play_text(self.complete_response)
            self.complete_response = ""  # Reset the complete response for the next interaction

def process_and_play_text():
    global concatenated_text
    # Use regular expression to split the text by '.' or '?' or '\n'
    sentences = re.split(r'[.?\n]+', concatenated_text)
    # Remove any empty strings that may result from split and strip whitespace
    sentences = [sentence.strip() for sentence in sentences if sentence]

    # Play each sentence using ElevenLabsManager
    for sentence in sentences:
        print(f"Playing: {sentence}")
        eleven_labs_manager.play_text(sentence)

    # Reset the concatenated text for the next interaction
    concatenated_text = ""

def interact_with_assistant(transcription):
    global last_thread_id, last_interaction_time
    print("Interacting with assistant...")  # Debug print

    # Instantiate CustomAssistantEventHandler
    custom_event_handler = CustomAssistantEventHandler(eleven_labs_manager)

    # Instantiate AssistantManager with required arguments
    assistant_manager = AssistantManager(openai_client, eleven_labs_manager, assistant_id="asst_3D8tACoidstqhbw5JE2Et2st")

    # Pass the custom event handler to AssistantManager
    assistant_manager.set_event_handler(custom_event_handler)

    # Check if a new thread needs to be created or if an existing one can be used
    if not last_thread_id or time.time() - last_interaction_time > 90:
        print("Creating new thread...")  # Debug print
        last_thread_id = assistant_manager.create_thread()
        assistant_manager.thread_id = last_thread_id
    else:
        print(f"Using existing thread: {last_thread_id}")  # Debug print

    last_interaction_time = time.time()
    instructions = f"Based on the transcription, interact with the user. Transcription: {transcription}"
    print(f"Sending instructions to assistant: {instructions}")  # Debug print

    # Assuming handle_streaming_interaction is the method to send instructions
    # and it's correctly implemented in AssistantManager.
    assistant_manager.handle_streaming_interaction(instructions)

def on_thread_message_completed(data):
    global processed_messages
    message_id = data.get('id')
    if message_id in processed_messages:
        print(f"Message {message_id} already processed.")
        return
    processed_messages.add(message_id)
    print("Handling ThreadMessageCompleted event...")
    # Extract and print the message content
    message_content = data.get('content', [])
    for content_block in message_content:
        if content_block['type'] == 'text':
            message_text = content_block['text']['value']
            print(f"Received message: {message_text}")
            # Use ElevenLabsManager to play back the text
            print(f"Playing message: {message_text}")  # Print statement before playing
            eleven_labs_manager.play_text(message_text)

# Map event types to handler functions
event_handlers = {
    'thread.message.completed': on_thread_message_completed,
    # Add other event handlers here as needed
}

# Dispatcher function
def dispatch_event(event_type, data):
    handler = event_handlers.get(event_type)
    if handler:
        handler(data)
    else:
        print(f"No handler for event type: {event_type}")

def on_thread_run_step_completed(data):
    # Extract the message content from the completed run step data
    message_content = data.get('content', [])
    # Initialize an empty string to accumulate the response text
    response_text = ""
    # Iterate through the content blocks to concatenate the text
    for content_block in message_content:
        if content_block['type'] == 'text':
            response_text += content_block['text']['value']
    # Check if the response text is not empty
    if response_text.strip():
        # Use ElevenLabsManager to play back the text
        print(f"Playing response: {response_text}")  # Print statement before playing
        eleven_labs_manager.play_text(response_text)
        print(f"Playing response: {response_text}")

def initialize():
    print("System initializing...")
    set_message_handler(handle_detected_words)
    setup_keyword_detection()

if __name__ == "__main__":
    initialize()
    while True:
        time.sleep(1)
        # Simulate receiving an event
        event_received = {
            'event': 'thread.message.completed',
            'data': {
                'id': 'msg_jsoCM86BSagjg4OzAjPKcwhx',
                'content': [
                    {
                        'text': {
                            'value': 'Hello! How can I assist you today?'
                        },
                        'type': 'text'
                    }
                ],
                # Other fields omitted for brevity
            }
        }
        dispatch_event(event_received['event'], event_received['data'])
