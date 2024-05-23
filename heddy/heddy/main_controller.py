import os
from heddy.ai_backend.zapier_manager import ZapierManager
from heddy.application_event import ApplicationEvent, ApplicationEventType, ProcessingStatus, Message
from heddy.io.sound_effects_player import AudioPlayer
from heddy.speech_to_text.stt_manager import STTManager
from heddy.text_to_speech.text_to_speach_manager import TTSManager
from heddy.word_detector import WordDetector
from heddy.io.audio_recorder import start_recording, stop_recording
from heddy.speech_to_text.assemblyai_transcriber import AssemblyAITranscriber
from heddy.ai_backend.assistant_manager import AssistantResultStatus, AssitsantResult, ThreadManager, StreamingManager
from heddy.text_to_speech.eleven_labs import ElevenLabsManager
from heddy.vision_module import VisionModule
import openai
from dotenv import load_dotenv
import uuid
import subprocess
import threading

class MainController:
    # State variables
    is_recording = False
    last_thread_id = None
    snapshot_taken = False
    snapshot_file_id = None
    
    # Global variable for transcription
    transcription = ""
    
    # Global set to track processed message IDs
    processed_messages = set()

    def __init__(
            self, 
            assistant,
            transcriber,
            synthesizer,
            audio_player,
            vision_module,
            word_detector
        ) -> None:
        self.assistant = assistant
        self.transcriber = transcriber
        self.synthesizer = synthesizer
        self.vision_module = vision_module
        self.audio_player = audio_player
        self.word_detector = word_detector
        print("MainController initialized")

    def process_event(self, event: ApplicationEvent):
        print(f"Processing event: {event}")
        if event.type == ApplicationEventType.START:
            return ApplicationEvent(
                ApplicationEventType.SYNTHESIZE,
                request='Hello! How can I assist you today?'
            )
        if event.type == ApplicationEventType.SYNTHESIZE:
            synthesized_event = self.synthesizer.synthesize(event)
            if synthesized_event is None:
                raise RuntimeError("Synthesize returned None")
            return ApplicationEvent(
                type=ApplicationEventType.PLAY,  # Transition to PLAY
                request=synthesized_event.result
            )
        if event.type == ApplicationEventType.PLAY:
            play_event = self.audio_player.play(event)
            if play_event is None:
                raise RuntimeError("Play returned None")
            return ApplicationEvent(
                type=ApplicationEventType.LISTEN,  # Transition to LISTEN
                request=play_event.result
            )
        if event.type == ApplicationEventType.LISTEN:
            detected_word_event = self.word_detector.listen(event)
            return self.handle_detected_word(detected_word_event.result)
        if event.type == ApplicationEventType.START_RECORDING:
            self.audio_player.play_sound("startrecording.wav")  # Play start recording sound
            self.start_recording()
            return ApplicationEvent(ApplicationEventType.LISTEN)
        if event.type == ApplicationEventType.USE_SNAPSHOT:
            self.audio_player.play_sound("tricorder.wav")  # Play take a picture sound
            self.vision_module.capture_image_async()
            self.vision_module.capture_complete.wait()  # Wait for capture to complete
            return ApplicationEvent(ApplicationEventType.GET_SNAPSHOT)
        if event.type == ApplicationEventType.STOP_RECORDING:
            self.audio_player.play_sound("respond.wav")  # Play stop recording/respond sound
            self.stop_recording()
            self.word_detector.clear()
            return ApplicationEvent(
                ApplicationEventType.TRANSCRIBE,
                request="recorded_audio.wav"
            )
        if event.type == ApplicationEventType.TRANSCRIBE:
            transcription_result = self.transcriber.transcribe_audio_file(event)
            transcription_text = transcription_result.result
            print(f"Transcription result: {transcription_text}")

            if self.snapshot_taken:
                file_id = self.snapshot_file_id
                self.snapshot_taken = False
                self.snapshot_file_id = None
                return self.assistant.handle_streaming_interaction(ApplicationEvent(
                    type=ApplicationEventType.AI_INTERACT,
                    request={"transcription_text": transcription_text, "snapshot_file_id": file_id}
                ))
            else:
                return ApplicationEvent(
                    type=ApplicationEventType.AI_INTERACT,  # Change to AI_INTERACT
                    request={"transcription_text": transcription_text}
                )
        if event.type == ApplicationEventType.GET_SNAPSHOT:
            return self.get_snapshot(event)
        if event.type in [ApplicationEventType.AI_INTERACT, ApplicationEventType.AI_TOOL_RETURN]:
            if self.snapshot_taken:
                print(f"Attaching snapshot with file ID: {self.snapshot_file_id} to message.")
                self.assistant.handle_streaming_interaction(ApplicationEvent(
                    type=event.type,
                    request={"result": event.result, "snapshot_file_id": self.snapshot_file_id}
                ))
                self.snapshot_taken = False
                self.snapshot_file_id = None
            result = self.assistant.handle_streaming_interaction(event)
            if result and result.type == ApplicationEventType.SYNTHESIZE:
                return result  # Return the SYNTHESIZE event to be processed
            return ApplicationEvent(ApplicationEventType.LISTEN)  # Transition back to LISTEN
        if event.type == ApplicationEventType.ZAPIER:
            return ZapierManager().handle_message(event)
        # Add more event types as needed
        return event
    
    def process_result(self, event: ApplicationEvent):
        print(f"Processing result: {event.type}, {event.status}, {event.result}")
        if event.status == ProcessingStatus.INIT:
            return event
        if event.type == ApplicationEventType.SYNTHESIZE:
            return ApplicationEvent(
                type=ApplicationEventType.SYNTHESIZE,
                status=ProcessingStatus.SUCCESS,
                result=event.result
            )
        # Add more event types as needed
        return event
    
    def handle_ai_result(self, result: AssitsantResult):
        if result.status == AssistantResultStatus.SUCCESS:
            print(f"Assistant Response: '{result.response}'")
            return ApplicationEvent(
                type=ApplicationEventType.SYNTHESIZE,
                request=result.response
            )
        elif result.status == AssistantResultStatus.ACTION_REQUIRED:
            tool_calls = result.calls["tools"]
            for tool_call in tool_calls:
                event = self.run(event=ApplicationEvent(
                    type=tool_call["type"],
                    request=tool_call["args"]
                ), process_result=self.process_func_trigger)
                tool_call["output"] = event.result
            return ApplicationEvent(
                type=ApplicationEventType.AI_TOOL_RETURN,
                request=result.calls
            )
        else:
            raise NotImplementedError(f"{result=}")
    
    def process_func_trigger(self, event: ApplicationEvent):
        return ApplicationEvent(
            type=ApplicationEventType.EXIT,
            result=event.result
        )
    
    def get_snapshot(self, event: ApplicationEvent):
        print("Processing get_snapshot")
        event.status = ProcessingStatus.SUCCESS
        file_id = self.vision_module.upload_image()
        if file_id:
            event.result = f"{event.request}\n\nImage File ID: {file_id}"
            print(f"Attaching image to message with file ID: {file_id}")
            self.snapshot_taken = True
            self.snapshot_file_id = file_id
        else:
            event.result = "Image upload failed."
        return event

    # TODO: move to an interaction manager(?) module
    def stop_recording(self, ):
        stop_recording()
        self.is_recording = False
        print("Recording stopped. Processing...")
    
    # TODO: move to an interaction manager(?) module
    def start_recording(self,):
        start_recording()
        self.is_recording = True
        print("Recording started...")
    
    # TODO: move to an interaction(?) module
    def handle_detected_word(self, word):
        if "snapshot" in word:
            print("Detected 'snapshot' keyword.")
            self.vision_module.capture_image_async()
            self.vision_module.capture_complete.wait()  # Wait for capture to complete
            self.snapshot_taken = True
            self.snapshot_file_id = self.vision_module.upload_image()
            print(f"Snapshot taken with file ID: {self.snapshot_file_id}")
            return ApplicationEvent(ApplicationEventType.LISTEN)
        if "computer" in word and not self.is_recording:
            return ApplicationEvent(ApplicationEventType.START_RECORDING)
        if "reply" in word and self.is_recording:
            return ApplicationEvent(ApplicationEventType.STOP_RECORDING)
        return ApplicationEvent(ApplicationEventType.LISTEN)
    
    def run(self, event: ApplicationEvent, process_result=None) -> ApplicationEvent:
        process_result = process_result or self.process_result
        current_event = event
        while current_event.type != ApplicationEventType.EXIT:
            print(current_event.type)
            if current_event.type == ApplicationEventType.START:
                self.audio_player.play_sound("listening.wav")  # Play start listening sound
            result = self.process_event(current_event)

            if result is None:
                raise RuntimeError("Processing event returned None")

            if event.status == ProcessingStatus.ERROR:
                raise RuntimeError(event.error)
            
            current_event = process_result(result)
        return current_event
        

def initialize():
    load_dotenv()
    print("System initializing...")
    # Initialize OpenAI client ok computer send a little zapier tick please reply
    openai_client = openai.OpenAI(
        api_key=os.getenv("OPENAI_API_KEY")
    ) # This line initializes openai_client with the openai library itself

    # Initialize modules with provided API keys
    assemblyai_transcriber = AssemblyAITranscriber(api_key=os.getenv("ASSEMBLYAI_API_KEY"))

    # Adjusted to use the hardcoded Assistant ID
    eleven_labs_manager = ElevenLabsManager(api_key=os.getenv("ELEVENLABS_API_KEY"))
    vision_module = VisionModule(openai_api_key=os.getenv("OPENAI_API_KEY"))

    # Initialize ThreadManager and StreamingManager
    thread_manager = ThreadManager(openai_client)
    streaming_manager = StreamingManager(thread_manager, eleven_labs_manager, assistant_id="asst_3D8tACoidstqhbw5JE2Et2st", openai_client=openai_client)

    word_detector = WordDetector()
    return MainController(
        assistant=streaming_manager,
        transcriber=STTManager(transcriber=assemblyai_transcriber),
        vision_module=vision_module,
        audio_player=AudioPlayer(),
        word_detector=word_detector,
        synthesizer=TTSManager(eleven_labs_manager)
    )

if __name__ == "__main__":
    main = initialize()
    main.run(ApplicationEvent(ApplicationEventType.START))
    main.run(ApplicationEvent(ApplicationEventType.START))
