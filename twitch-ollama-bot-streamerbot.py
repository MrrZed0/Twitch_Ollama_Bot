import aiohttp
import asyncio
import json
import random
import hmac
import hashlib
from fastapi import FastAPI, Request, Header
from twitchio.ext import commands
import threading
import uvicorn
import websockets

# ------------------------------------------
# CONFIGURATION
# ------------------------------------------
TWITCH_NICK = "YourBotUsername"
TWITCH_TOKEN = "oauth:xxxxxxxxxxxxxxxxxxxxxxxxxx"
TWITCH_CHANNEL = "your_channel"  # lowercase
CLIENT_ID = "your_twitch_client_id"
CLIENT_SECRET = "your_twitch_client_secret"
EVENTSUB_SECRET = "somesecretkey"
NGROK_URL = "https://abc123.ngrok.io"  # Your ngrok HTTPS URL
STREAMERBOT_WS_URL = "ws://localhost:8080"

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"

# ------------------------------------------
# Global queue for alerts
# ------------------------------------------
alert_queue = asyncio.Queue()

# ------------------------------------------
# OLLAMA AI QUERY
# ------------------------------------------
async def query_ollama(prompt):
    body = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.9}
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(OLLAMA_URL, json=body) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("response", "").strip()
            return "Yo, my AI brain crashed mid-thought 💀"

# ------------------------------------------
# Streamer.bot WS SEND
# ------------------------------------------
async def send_to_streamerbot(event_type, user_name):
    message = {
        "request": "DoAction",
        "action": "TwitchAlert",
        "args": {
            "type": event_type,
            "user": user_name
        }
    }
    try:
        async with websockets.connect(STREAMERBOT_WS_URL) as ws:
            await ws.send(json.dumps(message))
    except Exception as e:
        print(f"[Streamer.bot] WebSocket failed: {e}")

# ------------------------------------------
# TWITCH CHAT BOT
# ------------------------------------------
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

        # Ignore !commands here, only free chat gets AI reply
        if not content.startswith("!"):
            prompt = f"""
You're Bob Smith, a sarcastic, hype Twitch AI. Someone in chat named {author} just said: "{content}".
React in 1–2 short lines like you're part of the stream—never say you're AI.
"""
            reply = await query_ollama(prompt)
            await message.channel.send(reply)

        await self.handle_commands(message)

    @commands.command(name="roastme")
    async def roastme(self, ctx):
        prompt = f"Roast '{ctx.author.name}' like you're a Twitch chat legend. Funny, brutal, one-liner only."
        reply = await query_ollama(prompt)
        await ctx.send(reply)

    async def alert_listener(self):
        while True:
            alert = await alert_queue.get()
            channel = self.get_channel(TWITCH_CHANNEL)
            if channel:
                await channel.send(alert)

# ------------------------------------------
# FASTAPI EVENTSUB HANDLER
# ------------------------------------------
app = FastAPI()

@app.post("/eventsub/callback")
async def twitch_eventsub(request: Request,
                          twitch_eventsub_message_type: str = Header(None),
                          twitch_eventsub_message_signature: str = Header(None),
                          twitch_eventsub_message_id: str = Header(None),
                          twitch_eventsub_message_timestamp: str = Header(None)):
    raw_body = await request.body()
    body_str = raw_body.decode("utf-8")

    # Validate Twitch signature
    hmac_msg = twitch_eventsub_message_id + twitch_eventsub_message_timestamp + body_str
    expected_sig = "sha256=" + hmac.new(EVENTSUB_SECRET.encode(), hmac_msg.encode(), hashlib.sha256).hexdigest()

    if expected_sig != twitch_eventsub_message_signature:
        print("⚠️ Invalid signature")
        return {"error": "Unauthorized"}

    data = json.loads(body_str)

    if twitch_eventsub_message_type == "webhook_callback_verification":
        return {"challenge": data["challenge"]}

    event_type = data["subscription"]["type"]
    user = data["event"].get("user_name") or data["event"].get("broadcaster_user_name")

    # Alert logic
    if event_type == "channel.follow":
        msg = f"📢 {user} just followed!"
        await alert_queue.put(msg)
        await send_to_streamerbot("follow", user)

    elif event_type == "channel.subscribe":
        msg = f"🔥 {user} just subscribed!"
        await alert_queue.put(msg)
        await send_to_streamerbot("sub", user)

    elif event_type == "channel.subscription.gift":
        msg = f"🎁 {user} dropped a gift sub!"
        await alert_queue.put(msg)
        await send_to_streamerbot("gift", user)

    elif event_type == "channel.cheer":
        bits = data["event"]["bits"]
        msg = f"💸 {user} just cheered {bits} bits!"
        await alert_queue.put(msg)
        await send_to_streamerbot("bits", user)

    return {"status": "ok"}

# ------------------------------------------
# EVENTSUB SUBSCRIPTION SETUP
# ------------------------------------------
async def setup_eventsub():
    async with aiohttp.ClientSession() as session:
        token_resp = await session.post("https://id.twitch.tv/oauth2/token", params={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials"
        })
        tokens = await token_resp.json()

        headers = {
            "Authorization": f"Bearer {tokens['access_token']}",
            "Client-ID": CLIENT_ID,
            "Content-Type": "application/json"
        }

        topics = [
            {"type": "channel.follow", "version": "2"},
            {"type": "channel.subscribe", "version": "1"},
            {"type": "channel.subscription.gift", "version": "1"},
            {"type": "channel.cheer", "version": "1"},
        ]

        for topic in topics:
            payload = {
                "type": topic["type"],
                "version": topic["version"],
                "condition": {
                    "broadcaster_user_login": TWITCH_CHANNEL
                },
                "transport": {
                    "method": "webhook",
                    "callback": f"{NGROK_URL}/eventsub/callback",
                    "secret": EVENTSUB_SECRET
                }
            }
            resp = await session.post("https://api.twitch.tv/helix/eventsub/subscriptions",
                                      headers=headers, json=payload)
            print(f"Subscribed to {topic['type']}: {await resp.text()}")

# ------------------------------------------
# BOOT IT ALL
# ------------------------------------------
def start_fastapi():
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    threading.Thread(target=start_fastapi, daemon=True).start()
    asyncio.run(setup_eventsub())
    bot = TwitchBot()
    bot.run()
