import os
from heddy.application_event import ApplicationEvent, ApplicationEventType, ProcessingStatus
from heddy.io.sound_effects_player import AudioPlayer
from heddy.speech_to_text.stt_manager import STTManager
from heddy.text_to_speech.text_to_speach_manager import TTSManager
from heddy.word_detector import WordDetector
from heddy.io.audio_recorder import start_recording, stop_recording
from heddy.speech_to_text.assemblyai_transcriber import AssemblyAITranscriber
from heddy.ai_backend.assistant_manager import ThreadManager, StreamingManager
from heddy.text_to_speech.eleven_labs import ElevenLabsManager
from heddy.vision_module import VisionModule
import openai
from dotenv import load_dotenv


class MainController:
    # State variables
    is_recording = False
    picture_mode = False
    last_thread_id = None
    
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

    def process_event(self, event: ApplicationEvent):
        if event.type == ApplicationEventType.START:
            return ApplicationEvent(
                ApplicationEventType.SYNTHESIZE,
                request='Hello! How can I assist you today?'
            )
        if event.type == ApplicationEventType.SYNTHESIZE:
            return self.synthesizer.synthesize(event)
        if event.type == ApplicationEventType.PLAY:
            return self.audio_player.play(event)
        if event.type == ApplicationEventType.LISTEN:
            return self.word_detector.listen(event)
        if event.type == ApplicationEventType.START_RECORDING:
            self.audio_player.play_sound("startrecording.wav")  # Play start recording sound
            self.start_recording()
            return ApplicationEvent(ApplicationEventType.LISTEN)
        if event.type == ApplicationEventType.USE_SNAPSHOT:
            self.audio_player.play_sound("tricorder.wav")  # Play take a picture sound
            self.set_picture_mode()
            return ApplicationEvent(ApplicationEventType.LISTEN)
        if event.type == ApplicationEventType.STOP_RECORDING:
            self.audio_player.play_sound("respond.wav")  # Play stop recording/respond sound
            self.stop_recording()
            self.word_detector.clear()
            return ApplicationEvent(
                ApplicationEventType.TRANSCRIBE,
                request="recorded_audio.wav"
            )
        if event.type == ApplicationEventType.TRANSCRIBE:
            return self.transcriber.transcribe_audio_file(event)
        if event.type == ApplicationEventType.GET_SNAPSHOT:
            return self.get_snapshot(event)
        if event.type == ApplicationEventType.AI_INTERACT:
            return self.assistant.handle_streaming_interaction(event)

    def process_result(self, event: ApplicationEvent):
        if event.status == ProcessingStatus.ERROR:
            raise RuntimeError(event.error)
        if event.status == ProcessingStatus.INIT:
            return event
        if event.type == ApplicationEventType.SYNTHESIZE:
            return ApplicationEvent(
                type=ApplicationEventType.PLAY,
                request=event.result
            )
        if event.type == ApplicationEventType.PLAY:
            return ApplicationEvent(
                type=ApplicationEventType.LISTEN,
            )
        if event.type == ApplicationEventType.LISTEN:
            return self.handle_detected_word(event.result)
        if event.type == ApplicationEventType.TRANSCRIBE:
            print(f"Transcription result: '{event.result}'")
            if self.picture_mode:
                return ApplicationEvent(
                    type=ApplicationEventType.GET_SNAPSHOT,
                    request=event.result
                )
            else:
                return ApplicationEvent(
                type=ApplicationEventType.AI_INTERACT,
                request=event.result
            )
        if event.type == ApplicationEventType.GET_SNAPSHOT:
            print(f"Snapshot Result: '{event.result}'")
            return ApplicationEvent(
                type=ApplicationEventType.AI_INTERACT,
                request=event.result
            )
        if event.type == ApplicationEventType.AI_INTERACT:
            print(f"Assistant Response: '{event.result}'")
            return ApplicationEvent(
                type=ApplicationEventType.SYNTHESIZE,
                request=event.result
            )
    
    def get_snapshot(self, event: ApplicationEvent):
        # TODO: move to vision module logic
        self.picture_mode = False
        self.vision_module.capture_image_async()
        event.status = ProcessingStatus.SUCCESS
        event.result = self.vision_module.describe_captured_image(event.request)
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
    
    # TODO: move to an interaction manager(?) module
    def set_picture_mode(self,):
        if self.is_recording:
            self.picture_mode = True
            print("Picture mode activated")

    # TODO: move to an interaction(?) module
    def handle_detected_word(self, word):
        if "computer" in word and not self.is_recording:
            return ApplicationEvent(ApplicationEventType.START_RECORDING)
        if "snapshot" in word and not self.picture_mode:
            return ApplicationEvent(ApplicationEventType.USE_SNAPSHOT)
        if "reply" in word and self.is_recording:
            return ApplicationEvent(ApplicationEventType.STOP_RECORDING)
        return ApplicationEvent(ApplicationEventType.LISTEN)
    
    def run(self, event: ApplicationEvent):
        current_event = event
        while current_event.type != ApplicationEventType.EXIT:
            print(current_event.type)
            if current_event.type == ApplicationEventType.START:
                self.audio_player.play_sound("listening.wav")  # Play start listening sound
            result = self.process_event(current_event)
            current_event = self.process_result(result)

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
    streaming_manager = StreamingManager(thread_manager, eleven_labs_manager, assistant_id="asst_3D8tACoidstqhbw5JE2Et2st")

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