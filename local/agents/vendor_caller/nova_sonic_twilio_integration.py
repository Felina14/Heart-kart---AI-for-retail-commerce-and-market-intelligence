#!/usr/bin/env python3
"""
Nova Sonic + Twilio Integration
Real-time voice calls with bidirectional audio streaming
"""

import asyncio
import base64
import json
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Connect
from nova_sonic_voice_agent import NovaSonicVendorAgent
import websockets
from dotenv import load_dotenv

load_dotenv('../../.env')

app = Flask(__name__)

# Store active call sessions
active_sessions = {}


@app.route('/voice', methods=['POST'])
def voice_webhook():
    """
    Twilio webhook - called when incoming call arrives
    Returns TwiML to connect call to WebSocket
    """
    print("📞 Incoming call from Twilio")
    
    # Get call details
    from_number = request.form.get('From')
    to_number = request.form.get('To')
    call_sid = request.form.get('CallSid')
    
    print(f"   From: {from_number}")
    print(f"   To: {to_number}")
    print(f"   Call SID: {call_sid}")
    
    # Create TwiML response
    response = VoiceResponse()
    
    # Optional: Play greeting before connecting to WebSocket
    # response.say("Please wait while we connect you.", voice='Polly.Joanna')
    
    # Connect to WebSocket for bidirectional streaming
    connect = Connect()
    connect.stream(url=f'wss://your-server.com/media-stream/{call_sid}')
    response.append(connect)
    
    return str(response)


async def handle_twilio_media_stream(websocket, path):
    """
    Handle WebSocket connection from Twilio
    Forwards audio between Twilio and Nova Sonic
    """
    print(f"🔌 WebSocket connected: {path}")
    
    # Extract call_sid from path
    call_sid = path.split('/')[-1]
    
    # Create vendor context (in production, fetch from database)
    vendor_context = {
        'vendor_name': 'Holiday Decor Wholesale',
        'contact_person': 'Sarah',
        'purpose': 'place a purchase order',
        'order_details': {
            'items': ['Red Ornaments (100 units)', 'Gold Garland (50 units)'],
            'total_amount': 1250.00,
            'delivery_date': 'November 25th'
        }
    }
    
    # Create Nova Sonic agent
    agent = NovaSonicVendorAgent(vendor_context)
    
    try:
        # Start Nova Sonic session
        await agent.start_session()
        print("✅ Nova Sonic session started")
        
        # Start audio input
        await agent.start_audio_input()
        
        # Create task to handle Nova Sonic audio output
        async def forward_nova_to_twilio():
            """Forward audio from Nova Sonic to Twilio"""
            while agent.is_active:
                try:
                    # Get audio from Nova Sonic
                    audio_bytes = await agent.audio_queue.get()
                    
                    # Convert to mulaw for Twilio (8kHz)
                    # Note: You'll need to resample from 24kHz to 8kHz
                    # and convert PCM to mulaw format
                    audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
                    
                    # Send to Twilio
                    message = {
                        'event': 'media',
                        'streamSid': call_sid,
                        'media': {
                            'payload': audio_base64
                        }
                    }
                    await websocket.send(json.dumps(message))
                    
                except Exception as e:
                    print(f"Error forwarding to Twilio: {e}")
                    break
        
        # Start forwarding task
        forward_task = asyncio.create_task(forward_nova_to_twilio())
        
        # Handle incoming messages from Twilio
        async for message in websocket:
            data = json.loads(message)
            event = data.get('event')
            
            if event == 'start':
                print("📞 Call started")
                stream_sid = data['start']['streamSid']
                print(f"   Stream SID: {stream_sid}")
                
            elif event == 'media':
                # Get audio from Twilio (mulaw, 8kHz)
                audio_payload = data['media']['payload']
                audio_bytes = base64.b64decode(audio_payload)
                
                # Convert from mulaw to PCM 16kHz for Nova Sonic
                # Note: You'll need to resample and convert format
                
                # Send to Nova Sonic
                await agent.send_audio_chunk(audio_bytes)
                
            elif event == 'stop':
                print("📞 Call ended by Twilio")
                break
        
        # Cleanup
        agent.is_active = False
        forward_task.cancel()
        await agent.end_audio_input()
        await agent.end_session()
        
        # Get conversation summary
        summary = agent.get_conversation_summary()
        print("\n📊 Call Summary:")
        print(json.dumps(summary, indent=2))
        
    except Exception as e:
        print(f"❌ Error in WebSocket handler: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("🔌 WebSocket disconnected")


def start_websocket_server():
    """Start WebSocket server for Twilio connections"""
    print("🚀 Starting WebSocket server on port 8080...")
    
    async def serve():
        async with websockets.serve(handle_twilio_media_stream, "0.0.0.0", 8080):
            print("✅ WebSocket server running on ws://0.0.0.0:8080")
            await asyncio.Future()  # Run forever
    
    asyncio.run(serve())


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--websocket':
        # Run WebSocket server
        start_websocket_server()
    else:
        # Run Flask app for Twilio webhooks
        print("🚀 Starting Flask app for Twilio webhooks...")
        print("📝 Configure Twilio webhook URL: http://your-server.com/voice")
        print("💡 Run with --websocket flag to start WebSocket server")
        app.run(host='0.0.0.0', port=5000, debug=True)
