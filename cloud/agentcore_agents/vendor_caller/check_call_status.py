#!/usr/bin/env python3
"""
Check the status of the last Twilio call.
"""

import os
from dotenv import load_dotenv
from twilio.rest import Client

# Load environment
for env_path in ['../../.env', '../.env', '.env']:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break

TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

calls = client.calls.list(limit=5)

if calls:
    print("=" * 70)
    print("Recent Calls")
    print("=" * 70)
    for call in calls:
        print(f"\nCall SID:   {call.sid}")
        print(f"From:       {call.from_formatted}")
        print(f"To:         {call.to_formatted}")
        print(f"Status:     {call.status}")
        print(f"Direction:  {call.direction}")
        print(f"Duration:   {call.duration} seconds")
        print(f"Start Time: {call.start_time}")

        if call.status == 'failed':
            print(f"❌ FAILED — Error Code: {call.error_code}, Message: {call.error_message}")
        elif call.status == 'completed':
            print(f"✅ Completed successfully")
        elif call.status == 'busy':
            print(f"📞 Line was busy")
        elif call.status == 'no-answer':
            print(f"📵 No answer")
        else:
            print(f"⏳ Status: {call.status}")
else:
    print("No calls found")
