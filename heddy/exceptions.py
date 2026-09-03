"""Exception hierarchy shared across the package."""


class HeddyError(Exception):
    """Base class for recoverable errors raised by pipeline components.

    The controller converts these into failed events and goes back to listening
    instead of crashing the main loop.
    """


class ConfigError(HeddyError):
    """Raised when required configuration is missing or invalid."""


class RecordingError(HeddyError):
    """Raised when the microphone could not be captured."""


class AssistantError(HeddyError):
    """Raised when the language-model request fails or returns nothing usable."""
