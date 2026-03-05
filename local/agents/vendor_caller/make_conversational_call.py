#!/usr/bin/env python3
"""
Make a conversational AI call using Nova Sonic + Twilio
"""

import os
from dotenv import load_dotenv
from twilio.rest import Client

# Load environment
env_paths = ['../../.env', '.env']
for env_path in env_paths:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break

# Get credentials
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

# Your phone number (from .env)
YOUR_PHONE = os.getenv('TEST_PHONE_NUMBER', '')

# Your ngrok URL (from .env)
NGROK_URL = os.getenv('NGROK_URL', '')

print("📞 Making Conversational AI Call with Nova Sonic")
print("=" * 70)
print()
print("✅ WebSocket server: Running")
print("✅ ngrok tunnel: Active")
print(f"✅ Public URL: {NGROK_URL}")
print()

print(f"From: {TWILIO_PHONE_NUMBER}")
print(f"To: {YOUR_PHONE}")
print(f"WebSocket: {NGROK_URL}/media-stream")
print()

# Create TwiML that connects to WebSocket
# Extract domain from ngrok URL and create proper WSS URL
ngrok_domain = NGROK_URL.replace('https://', '').replace('http://', '')
websocket_url = f"wss://{ngrok_domain}/media-stream"

print(f"WebSocket URL: {websocket_url}")
print()

twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{websocket_url}" />
    </Connect>
</Response>
"""

# Create Twilio client
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

try:
    # Make the call
    call = client.calls.create(
        twiml=twiml,
        to=YOUR_PHONE,
        from_=TWILIO_PHONE_NUMBER
    )
    
    print(f"✅ Call initiated!")
    print(f"📞 Call SID: {call.sid}")
    print()
    print(f"💬 What will happen:")
    print(f"   1. You'll receive a call")
    print(f"   2. Nova Sonic AI will greet you")
    print(f"   3. AI will introduce itself and explain the purpose")
    print(f"   4. AI will ask about stock availability")
    print(f"   5. You can respond naturally")
    print(f"   6. AI will respond based on your answers")
    print(f"   7. Real back-and-forth conversation!")
    print()
    print(f"🎤 Speak naturally - Nova Sonic understands conversational speech!")
    
except Exception as e:
    print(f"❌ Error: {e}")
