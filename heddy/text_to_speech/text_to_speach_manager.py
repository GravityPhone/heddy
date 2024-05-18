from dataclasses import dataclass
from enum import Enum
from typing import Optional
from heddy.application_event import ApplicationEvent, ApplicationEventType, ProcessingStatus

class TTSStatus(Enum):
    SUCCESS = 1
    ERROR = -1

@dataclass
class TTSResult:
    # TODO: change to generic audio type so we could play different formats
    status: TTSStatus
    audio: Optional[bytes] = None
    error: Optional[str] = None
    
class TTSManager:
    def __init__(self, synthesizer):
        self.synthesizer = synthesizer
    
    def synthesize(self, event: ApplicationEvent):
        result: TTSResult = self.synthesizer(event.request)

        if result.status == TTSStatus.SUCCESS:
            event.result = result.audio
            event.status = ProcessingStatus.SUCCESS
        else:
            event.error = result.error
            event.status = ProcessingStatus.ERROR
        
        return event
