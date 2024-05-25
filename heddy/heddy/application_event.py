from dataclasses import dataclass
from enum import Enum
from typing import Optional
from traitlets import Any

class ApplicationEventType(Enum):
    EXIT = -1
    START = 0
    SYNTHESIZE = 1
    PLAY = 2
    LISTEN = 3
    START_RECORDING = 4
    USE_SNAPSHOT = 5
    STOP_RECORDING = 6
    TRANSCRIBE = 7
    GET_SNAPSHOT = 8
    AI_INTERACT = 9
    AI_TOOL_RETURN = 10
    ZAPIER = 11
    ERROR = -2  # Added this line with a numeric value

class ProcessingStatus(Enum):
    INIT = 0
    SUCCESS = 1
    ERROR = -1

@dataclass
class ApplicationEvent:
    type: ApplicationEventType
    request: Optional[Any] = None
    result: Optional[Any] = None
    error: Optional[str] = ""
    status: ProcessingStatus = ProcessingStatus.INIT

@dataclass
class Message:
    id: str
    role: str
    content: str
    status: ProcessingStatus = ProcessingStatus.INIT
