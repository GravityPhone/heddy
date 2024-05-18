from dataclasses import dataclass
from enum import Enum
from typing import Optional
from traitlets import Any

class ApplicationEventType(Enum):
    START = "start"
    SYNTHESIZE = "synthesize"
    AI_INTERACT = "ai_interact"
    AI_TOOL_RETURN = "ai_tool_return"

class ProcessingStatus(Enum):
    INIT = "init"
    SUCCESS = "success"
    ERROR = "error"

class ApplicationEvent:
    def __init__(self, type, status=ProcessingStatus.INIT, request=None, result=None, error=None):
        self.type = type
        self.status = status
        self.request = request
        self.result = result
        self.error = error

@dataclass
class Message:
    id: str
    role: str
    content: str
    status: ProcessingStatus = ProcessingStatus.INIT
