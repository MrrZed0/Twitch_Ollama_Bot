import aiohttp
import asyncio
import json
import random
import hmac
import hashlib
from fastapi import FastAPI, Request, Header
from twitchio.ext import commands
from datetime import datetime
import threading
import uvicorn

# ------------- CONFIG -------------
TWITCH_NICK = "YourBotUsername"
TWITCH_TOKEN = "oauth:xxxxxxxxxxxxxxxxxxxxx"
TWITCH_CHANNEL = "yourchannel"
CLIENT_ID = "your_twitch_client_id"
CLIENT_SECRET = "your_twitch_client_secret"
EVENTSUB_SECRET = "your_eventsub_shared_secret"
NGROK_URL = "https://your-ngrok-url.ngrok.io"

OLLAMA_MODEL = "llama3"
OLLAMA_URL = "http://localhost:11434/api/generate"

# Shared queue to pass alerts from webhook -> bot
alert_queue = asyncio.Queue()

# ----------- OLLAMA FUNCTION -----------
async def query_ollama(prompt):
    headers = {"Content-Type": "application/json"}
    data = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.9}
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(OLLAMA_URL, headers=headers, data=json.dumps(data)) as response:
            if response.status != 200:
                return "Lag spike hit the AI again 💀"
            result = await response.json()
            return result.get("response", "").strip()

# -------------- TWITCH BOT --------------
class TwitchBot(commands.Bot):

    def __init__(self):
        super().__init__(token=TWITCH_TOKEN, prefix="!", initial_channels=[TWITCH_CHANNEL])

    async def event_ready(self):
        print(f"[✅] Logged in as {self.nick}")
        self.loop.create_task(self.alert_listener())

    async def event_message(self, message):
        if message.echo:
            return

        content = message.content.strip()
        author = message.author.name

        if not content.startswith("!"):
            prompt = f"""
You're Bob Smith, a chaotic, sarcastic AI assistant for a Twitch streamer. You're funny, hype, and human-sounding.

User: {author}
Message: {content}

Respond as if you're in the Twitch chat—short, funny, helpful, or teasing.
"""
            reply = await query_ollama(prompt)
            if reply:
                await message.channel.send(reply)

        await self.handle_commands(message)

    @commands.command(name="roastme")
    async def roastme(self, ctx):
        prompt = f"""
You're Bob Smith. Roast the Twitch user '{ctx.author.name}' with a savage, hilarious one-liner. Be spicy. No filters.
"""
        reply = await query_ollama(prompt)
        await ctx.send(reply)

    async def alert_listener(self):
        while True:
            alert = await alert_queue.get()
            channel = self.get_channel(TWITCH_CHANNEL)
            if channel:
                await channel.send(alert)

# -------------- EVENTSUB SERVER --------------
app = FastAPI()

@app.post("/eventsub/callback")
async def twitch_eventsub(request: Request, 
                          twitch_eventsub_message_type: str = Header(None),
                          twitch_eventsub_message_signature: str = Header(None),
                          twitch_eventsub_message_id: str = Header(None),
                          twitch_eventsub_message_timestamp: str = Header(None)):
    raw_body = await request.body()
    body = raw_body.decode("utf-8")

    # --- Validate signature
    hmac_message = twitch_eventsub_message_id + twitch_eventsub_message_timestamp + body
    expected_signature = "sha256=" + hmac.new(EVENTSUB_SECRET.encode(), hmac_message.encode(), hashlib.sha256).hexdigest()

    if expected_signature != twitch_eventsub_message_signature:
        print("⚠️ Signature mismatch!")
        return {"error": "invalid signature"}

    data = json.loads(body)

    # --- Handle Twitch EventSub handshake
    if twitch_eventsub_message_type == "webhook_callback_verification":
        return {"challenge": data["challenge"]}

    event_type = data["subscription"]["type"]
    user = data["event"].get("user_name") or data["event"].get("broadcaster_user_name")

    # --- Handle events
    if event_type == "channel.follow":
        await alert_queue.put(f"📢 New follow from {user}! Welcome to the squad.")
    elif event_type == "channel.subscribe":
        await alert_queue.put(f"🔥 {user} just subbed! W energy!")
    elif event_type == "channel.subscription.gift":
        await alert_queue.put(f"🎁 {user} just dropped a gift sub! Spreadin' the love!")
    elif event_type == "channel.cheer":
        bits = data['event']['bits']
        await alert_queue.put(f"💸 {user} just cheered {bits} bits! LET’S GO!")
    return {"status": "ok"}

# -------------- EVENTSUB SETUP HELPER --------------
async def setup_eventsub():
    async with aiohttp.ClientSession() as session:
        # Get OAuth token
        resp = await session.post("https://id.twitch.tv/oauth2/token", params={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials"
        })
        auth = await resp.json()
        headers = {
            "Authorization": f"Bearer {auth['access_token']}",
            "Client-ID": CLIENT_ID,
            "Content-Type": "application/json"
        }

        # Define subscription topics
        topics = [
            {"type": "channel.follow", "version": "2"},
            {"type": "channel.subscribe", "version": "1"},
            {"type": "channel.subscription.gift", "version": "1"},
            {"type": "chan
