import numpy as np
import simpleaudio as sa

def play_tone(frequency=440.0, duration=1.0, sample_rate=44100, volume=0.5):
    """
    Play a tone using simpleaudio.

    Parameters:
    - frequency: The frequency of the tone in Hertz.
    - duration: How long the tone plays for in seconds.
    - sample_rate: Number of audio samples per second.
    - volume: Volume of the tone, ranging from 0.0 to 1.0.
    """
    # Generate array with duration*sample_rate steps, ranging between 0 and duration
    t = np.linspace(0, duration, int(sample_rate * duration), False)

    # Generate a sine wave of the specified frequency
    note = np.sin(frequency * t * 2 * np.pi)

    # Ensure that highest value is in 16-bit range
    audio = note * (32767 * volume)
    audio = audio.astype(np.int16)  # Convert to 16-bit data

    # Start playback
    play_obj = sa.play_buffer(audio, 1, 2, sample_rate)

    # Wait for playback to finish before exiting
    play_obj.wait_done()

if __name__ == "__main__":
    print("Playing test tone...")
    play_tone()
