"""A minimal container for raw PCM audio."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PcmAudio:
    """Signed 16-bit little-endian PCM samples, ready to be written to an output stream."""

    data: bytes
    sample_rate: int
    channels: int = 1
    sample_width: int = 2

    @property
    def frame_size(self) -> int:
        """Bytes per frame (one sample for every channel)."""
        return self.channels * self.sample_width

    @property
    def duration(self) -> float:
        """Length of the audio in seconds."""
        return len(self.data) / (self.sample_rate * self.frame_size)
