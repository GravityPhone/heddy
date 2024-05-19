from dataclasses import dataclass
from enum import Enum
from typing import Optional

class ApplicationEventType(Enum):
    START = "start"
    SYNTHESIZE = "synthesize"
    AI_INTERACT = "ai_interact"
    AI_TOOL_RETURN = "ai_tool_return"
    PLAY = "play"  # Added this line
    EXIT = "exit"  # Added this line

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
