#!/usr/bin/env python3
"""
Nova Sonic + Twilio WebSocket Server
Real-time conversational AI phone calls
"""

import asyncio
import base64
import json
import os
import audioop
from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
import websockets
from dotenv import load_dotenv
from nova_sonic_voice_agent import NovaSonicVendorAgent

load_dotenv('../../.env')

# Audio conversion state for better quality
conversion_state_in = None
conversion_state_out = None

# Audio conversion functions with better error handling
def mulaw_to_pcm(mulaw_data, sample_rate_in=8000, sample_rate_out=16000):
    """Convert mulaw audio to PCM and resample - OPTIMIZED for smooth playback"""
    global conversion_state_in
    
    try:
        # Ensure data length is valid
        if len(mulaw_data) == 0:
            return b''
        
        # Decode mulaw to PCM (16-bit)
        pcm_data = audioop.ulaw2lin(mulaw_data, 2)
        
        # Resample from 8kHz to 16kHz with state preservation
        if sample_rate_in != sample_rate_out:
            pcm_data, conversion_state_in = audioop.ratecv(
                pcm_data, 2, 1, sample_rate_in, sample_rate_out, conversion_state_in
            )
        
        return pcm_data
    except Exception as e:
        print(f"⚠️  mulaw_to_pcm error: {e}")
        # Reset state on error
        conversion_state_in = None
        return b''

def pcm_to_mulaw(pcm_data, sample_rate_in=24000, sample_rate_out=8000):
    """Convert PCM audio to mulaw and resample - OPTIMIZED for smooth playback"""
    global conversion_state_out
    
    try:
        # Ensure data length is valid and even (16-bit samples)
        if len(pcm_data) == 0:
            return b''
        
        if len(pcm_data) % 2 != 0:
            pcm_data = pcm_data[:-1]  # Trim last byte if odd
        
        # Resample from 24kHz to 8kHz with state preservation
        if sample_rate_in != sample_rate_out:
            pcm_data, conversion_state_out = audioop.ratecv(
                pcm_data, 2, 1, sample_rate_in, sample_rate_out, conversion_state_out
            )
        
        # Encode PCM to mulaw
        mulaw_data = audioop.lin2ulaw(pcm_data, 2)
        
        return mulaw_data
    except Exception as e:
        print(f"⚠️  pcm_to_mulaw error: {e}")
        # Reset state on error
        conversion_state_out = None
        return b''

app = Flask(__name__)

# Store active call sessions
active_calls = {}


@app.route('/voice', methods=['POST'])
def voice_webhook():
    """
    Twilio webhook - called when call is answered
    Returns TwiML to connect call to WebSocket
    """
    call_sid = request.form.get('CallSid')
    from_number = request.form.get('From')
    to_number = request.form.get('To')
    
    print(f"\n📞 Incoming call:")
    print(f"   Call SID: {call_sid}")
    print(f"   From: {from_number}")
    print(f"   To: {to_number}")
    
    # Create TwiML response
    response = VoiceResponse()
    
    # Connect to WebSocket for bidirectional streaming
    connect = Connect()
    stream = Stream(url=f'wss://your-ngrok-url.ngrok.io/media-stream')
    connect.append(stream)
    response.append(connect)
    
    return str(response)


@app.route('/gather', methods=['POST'])
def gather_webhook():
    """
    Handle user input after pressing a key
    """
    digits = request.form.get('Digits')
    call_sid = request.form.get('CallSid')
    
    print(f"\n🔢 User pressed: {digits}")
    print(f"   Call SID: {call_sid}")
    
    response = VoiceResponse()
    
    if digits == '1':
        # User pressed 1, connect to WebSocket for conversation
        print("   ✅ Connecting to conversational AI...")
        
        # Get ngrok URL from environment
        ngrok_url = os.getenv('NGROK_URL', 'wss://your-ngrok-url.ngrok-free.dev')
        ws_url = ngrok_url.replace('https://', 'wss://').replace('http://', 'ws://')
        
        connect = Connect()
        stream = Stream(url=f'{ws_url}/media-stream')
        connect.append(stream)
        response.append(connect)
    else:
        # Invalid input
        response.say(
            "Invalid input. Goodbye!",
            voice='Polly.Joanna'
        )
    
    return str(response)


@app.route('/call-status', methods=['POST'])
def call_status():
    """Handle call status updates"""
    call_sid = request.form.get('CallSid')
    call_status = request.form.get('CallStatus')
    
    print(f"\n📊 Call status update:")
    print(f"   Call SID: {call_sid}")
    print(f"   Status: {call_status}")
    
    return '', 200


async def handle_twilio_stream(websocket):
    """
    Handle WebSocket connection from Twilio
    Bridges audio between Twilio and Nova Sonic
    """
    print(f"\n🔌 WebSocket connected")
    
    call_sid = None
    stream_sid = None
    agent = None
    
    try:
        async for message in websocket:
            data = json.loads(message)
            event = data.get('event')
            
            if event == 'start':
                # Call started
                call_sid = data['start']['callSid']
                stream_sid = data['start']['streamSid']
                
                print(f"\n📞 Call started:")
                print(f"   Call SID: {call_sid}")
                print(f"   Stream SID: {stream_sid}")
                
                # Create vendor context
                vendor_context = {
                    'vendor_name': 'Holiday Decor Wholesale',
                    'contact_person': 'there',
                    'purpose': 'place a purchase order',
                    'order_details': {
                        'items': [
                            {'name': 'Red Glass Ornaments', 'quantity': 100},
                            {'name': 'Gold Garland', 'quantity': 50}
                        ],
                        'total_amount': 1250.00,
                        'delivery_date': 'November 25th'
                    }
                }
                
                # Create Nova Sonic agent
                agent = NovaSonicVendorAgent(vendor_context)
                
                # Start Nova Sonic session
                await agent.start_session()
                print("✅ Nova Sonic session started")
                
                # Start audio input for Nova Sonic
                await agent.start_audio_input()
                
                # Start task to forward Nova Sonic audio to Twilio
                async def forward_to_twilio():
                    """Forward audio from Nova Sonic to Twilio - NO BUFFERING for smooth playback"""
                    
                    while agent.is_active:
                        try:
                            # Get audio from Nova Sonic (24kHz PCM)
                            audio_bytes = await agent.audio_queue.get()
                            
                            if not audio_bytes:
                                continue
                            
                            # Convert from 24kHz PCM to 8kHz mulaw for Twilio
                            try:
                                # Ensure audio is in correct format
                                if len(audio_bytes) % 2 != 0:
                                    # Pad if odd length
                                    audio_bytes = audio_bytes + b'\x00'
                                
                                mulaw_audio = pcm_to_mulaw(audio_bytes, sample_rate_in=24000, sample_rate_out=8000)
                                
                                # Send IMMEDIATELY - no buffering for smooth playback
                                audio_base64 = base64.b64encode(mulaw_audio).decode('utf-8')
                                
                                message = {
                                    'event': 'media',
                                    'streamSid': stream_sid,
                                    'media': {
                                        'payload': audio_base64
                                    }
                                }
                                await websocket.send(json.dumps(message))
                                
                                # Small delay to prevent overwhelming the connection
                                await asyncio.sleep(0.001)  # 1ms delay
                                    
                            except Exception as conv_error:
                                print(f"⚠️  Audio conversion error: {conv_error}")
                                continue
                            
                        except asyncio.CancelledError:
                            break
                        except Exception as e:
                            print(f"❌ Error forwarding to Twilio: {e}")
                            break
                
                # Start forwarding task
                forward_task = asyncio.create_task(forward_to_twilio())
                active_calls[call_sid] = {
                    'agent': agent,
                    'forward_task': forward_task
                }
                
            elif event == 'media':
                # Incoming audio from Twilio (8kHz mulaw)
                if agent and agent.is_active:
                    try:
                        audio_payload = data['media']['payload']
                        mulaw_audio = base64.b64decode(audio_payload)
                        
                        if not mulaw_audio:
                            continue
                        
                        # Convert from 8kHz mulaw to 16kHz PCM for Nova Sonic
                        try:
                            pcm_audio = mulaw_to_pcm(mulaw_audio, sample_rate_in=8000, sample_rate_out=16000)
                            await agent.send_audio_chunk(pcm_audio)
                        except Exception as conv_error:
                            print(f"⚠️  Incoming audio conversion error: {conv_error}")
                            # Skip this chunk rather than sending corrupted audio
                            continue
                    except Exception as e:
                        print(f"⚠️  Error processing incoming audio: {e}")
                        continue
                    
            elif event == 'stop':
                # Call ended
                print(f"\n📞 Call ended: {call_sid}")
                
                if call_sid in active_calls:
                    call_data = active_calls[call_sid]
                    agent = call_data['agent']
                    forward_task = call_data['forward_task']
                    
                    # Stop agent
                    agent.is_active = False
                    forward_task.cancel()
                    
                    await agent.end_audio_input()
                    await agent.end_session()
                    
                    # Get conversation summary
                    summary = agent.get_conversation_summary()
                    print("\n📊 Call Summary:")
                    print(json.dumps(summary, indent=2))
                    
                    del active_calls[call_sid]
                
                break
                
    except Exception as e:
        print(f"❌ Error in WebSocket handler: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("🔌 WebSocket disconnected")


def start_websocket_server(port=8080):
    """Start WebSocket server for Twilio connections"""
    print(f"\n🚀 Starting WebSocket server on port {port}...")
    print(f"📡 WebSocket URL: ws://localhost:{port}/media-stream")
    print(f"\n💡 Next steps:")
    print(f"   1. Run ngrok: ngrok http {port}")
    print(f"   2. Update the webhook URL in voice_webhook() with your ngrok URL")
    print(f"   3. Make a test call")
    print()
    
    async def serve():
        async with websockets.serve(handle_twilio_stream, "0.0.0.0", port):
            print(f"✅ WebSocket server running!")
            await asyncio.Future()  # Run forever
    
    asyncio.run(serve())


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--websocket':
        # Run WebSocket server
        start_websocket_server(port=8080)
    else:
        # Run Flask app for Twilio webhooks
        print("\n🚀 Starting Flask app for Twilio webhooks...")
        print("📝 Twilio webhook URL: http://your-ngrok-url.ngrok.io/voice")
        print("\n💡 In another terminal, run:")
        print("   python3 nova_sonic_twilio_server.py --websocket")
        print()
        app.run(host='0.0.0.0', port=5000, debug=False)
