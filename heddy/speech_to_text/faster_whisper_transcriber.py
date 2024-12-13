from faster_whisper import WhisperModel

from heddy.speech_to_text.stt_manager import STTResult, STTStatus


class WhisperTranscriber:
    def __init__(
            self,
            model_size="medium",
            device="cpu",
            compute_type="int8"
        ) -> None:
        self.whisper_model = WhisperModel(
            model_size_or_path=model_size,
            device=device,
            compute_type=compute_type
        )
    
    def transcribe_audio_file(self, audio_file_path):
        try:
            segments, info = self.whisper_model.transcribe(audio_file_path, beam_size=4)
            segments = [segment.text for segment in segments]
            text = "".join(segments)
        except Exception as e:
            return STTResult(
                text="",
                error=str(e),
                status=STTStatus.ERROR
            )
        return STTResult(
            text=text,
            error="",
            status=STTStatus.SUCCESS
        )