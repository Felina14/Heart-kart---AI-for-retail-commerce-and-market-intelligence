#!/usr/bin/env python3
"""
Make a conversational AI call using Nova Sonic + Twilio.

Usage:
    python make_conversational_call.py                   # Call default number
    python make_conversational_call.py +919094840869     # Call specific number
"""

import os
import sys
from dotenv import load_dotenv
from twilio.rest import Client

# Load environment
for env_path in ['../../.env', '../.env', '.env']:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break

# Get credentials
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
NGROK_URL = os.getenv('NGROK_URL', '')

# Target phone number
TARGET_PHONE = sys.argv[1] if len(sys.argv) > 1 else os.getenv('VENDOR_PHONE', '+919094840869')

print("📞 Making Conversational AI Call with Nova Sonic")
print("=" * 70)
print()
print(f"✅ Public URL: {NGROK_URL}")
print(f"From: {TWILIO_PHONE_NUMBER}")
print(f"To: {TARGET_PHONE}")

# Create TwiML that connects to WebSocket
ngrok_domain = NGROK_URL.replace('https://', '').replace('http://', '')
websocket_url = f"wss://{ngrok_domain}/media-stream"
print(f"WebSocket: {websocket_url}")
print()

twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{websocket_url}" />
    </Connect>
</Response>
"""

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

try:
    call = client.calls.create(
        twiml=twiml,
        to=TARGET_PHONE,
        from_=TWILIO_PHONE_NUMBER,
    )
    print(f"✅ Call initiated!")
    print(f"📞 Call SID: {call.sid}")
    print()
    print(f"💬 What will happen:")
    print(f"   1. Vendor receives a call")
    print(f"   2. Nova Sonic AI (Priya) greets them")
    print(f"   3. AI states the purchase order")
    print(f"   4. Vendor responds naturally")
    print(f"   5. AI confirms or handles decline")
    print()
    print(f"🎤 Real-time bidirectional conversation via Nova Sonic!")

except Exception as e:
    print(f"❌ Error: {e}")
