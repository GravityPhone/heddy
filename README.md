# Heddy

A hands-free AI assistant built into a baseball cap.

A Raspberry Pi in the hat listens through a microphone and talks back through a bone-conduction speaker. Say **"computer"**, ask your question, then say **"reply"**, and Heddy answers out loud in a custom ElevenLabs voice. Say **"snapshot"** while you're asking and it takes a picture with the hat's camera, so you can ask about what you're looking at.

It can also send text messages for you ("text Sam that I'm running late") through a Zapier webhook.

## What it uses

- PocketSphinx for the wake words (runs on the device)
- AssemblyAI for speech to text
- OpenAI for the answers and for looking at pictures
- ElevenLabs for the voice
- Zapier for sending texts (optional)

## Setup

```bash
git clone https://github.com/GravityPhone/heddy.git
cd heddy
pip install -e .
cp .env.example .env    # add your OpenAI, AssemblyAI and ElevenLabs keys
heddy
```

To use your own voice, set `ELEVENLABS_VOICE_ID` in `.env`. To turn on texting, set `ZAPIER_WEBHOOK_URL`. The wake words live in `heddy/resources/keywords.kws`.

Conversations remember context for 90 seconds, then start fresh.
