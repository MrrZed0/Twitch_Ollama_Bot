# Twitch_Ollama_Bot

# What This Does:
Feature	Included
Twitch chat interaction	✅
AI responses via Ollama	✅
!roastme command	✅
Follows, Subs, Bits alerts via EventSub	✅
Webhook server for EventSub	✅ (FastAPI + ngrok compatible)
Custom alerts in chat	✅
Easy deployment	✅


# How It Works
TwitchIO bot connects to chat and handles !commands and AI replies.

FastAPI server listens for Twitch EventSub webhooks (follows, subs, bits).

Event data is sent to the chat bot via an in-memory queue.

The bot reads alerts and sends messages into Twitch chat



# Required Setup
1: Install all required packages:
`pip install twitchio fastapi aiohttp uvicorn websockets`

2: Start ngrok (for webhook)
`ngrok http 8000`
Use the HTTPS URL from ngrok (e.g. https://abc123.ngrok.io) in Twitch.



# Final Setup Steps

1: Replace:
`TWITCH_NICK, TWITCH_TOKEN, TWITCH_CHANNEL`
`CLIENT_ID, CLIENT_SECRET, EVENTSUB_SECRET`
`NGROK_URL with your public https:// ngrok address`

2: Run the script:
`python3 twitch-ollama-bot.py`

3) Your bot will:

- Join chat

- Respond to chat with AI

- React to follows, subs, gifts, and bits with hype messages

- Work with Ollama locally

___________________________________________________________________________________________
# Twitch Ollama Bot Connected With Streamer.bot

Python Script: Twitch + Ollama + EventSub + Streamer.bot Integration

# This script connects:
- Twitch chat (via TwitchIO)
- Ollama AI (local model for chat responses)
- Twitch EventSub (for follows, subs, bits)
- Streamer.bot WebSocket (to send alerts)

  
# Streamer.bot Setup Script (WebSocket Listener)

# In Streamer.bot:

- Go to Actions → Create new Action → call it: TwitchAlert

- Add a Sub-Action → Text to Speech or Show on Stream or OBS source etc.

- Use these variable references:

`{args.type} → "follow", "sub", "bits", "gift"`

`{args.user} → Twitch username`

# Example: TTS Message

In Text to Speech:
`{args.user} just {if:{args.type} == "sub":subscribed}{if:{args.type} == "follow":followed}{if:{args.type} == "gift":gifted a sub}{if:{args.type} == "bits":dropped bits}! Let's go!`

