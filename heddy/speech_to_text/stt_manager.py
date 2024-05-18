from dataclasses import dataclass
from typing import Optional
from enum import Enum

from heddy.application_event import ApplicationEvent, ProcessingStatus

class STTStatus(Enum):
    SUCCESS = 1
    ERROR = -1

@dataclass
class STTResult:
    text: Optional[str]
    error: Optional[str]
    status: STTStatus

class STTManager:
    def __init__(self, transcriber) -> None:
        self.transcriber = transcriber

    def transcribe_audio_file(self, event: ApplicationEvent):
        result: STTResult = self.transcriber.transcribe_audio_file(event.request)
        if result.status == STTStatus.SUCCESS:
            event.result = result.text
            event.status = ProcessingStatus.SUCCESS
        else:
            event.result = result.error
            event.status = ProcessingStatus.ERROR
        return event
    