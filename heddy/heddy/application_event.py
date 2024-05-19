from dataclasses import dataclass
from enum import Enum
from typing import Optional

class ApplicationEventType(Enum):
    START = "start"
    SYNTHESIZE = "synthesize"
    AI_INTERACT = "ai_interact"
    AI_TOOL_RETURN = "ai_tool_return"
    PLAY = "play"
    LISTEN = "listen"
    START_RECORDING = "start_recording"
    STOP_RECORDING = "stop_recording"
    USE_SNAPSHOT = "use_snapshot"
    TRANSCRIBE = "transcribe"
    GET_SNAPSHOT = "get_snapshot"  # Added this line
    EXIT = "exit"

class ProcessingStatus(Enum):
    INIT = "init"
    SUCCESS = "success"
    ERROR = "error"

@dataclass
class ApplicationEvent:
    type: ApplicationEventType
    status: ProcessingStatus = ProcessingStatus.INIT
    request: Optional[dict] = None
    result: Optional[dict] = None
    error: Optional[str] = None

@dataclass
class Message:
    id: str
    role: str
    content: str
    status: ProcessingStatus = ProcessingStatus.INIT
