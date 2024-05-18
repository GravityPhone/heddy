from elevenlabs import play
from elevenlabs.client import ElevenLabs

client = ElevenLabs(
  api_key="YOUR_API_KEY",  # Replace YOUR_API_KEY with your actual API key
)

audio = client.generate(
  text="Hello! 你好! Hola! नमस्ते! Bonjour! こんにちは! مرحبا! 안녕하세요! Ciao! Cześć! Привіт! வணக்கம்!",
  voice="Rachel",
  model="eleven_multilingual_v2"
)
play(audio)
