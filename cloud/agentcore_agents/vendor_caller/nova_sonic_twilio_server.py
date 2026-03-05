#!/usr/bin/env python3
"""
Nova Sonic + Twilio WebSocket Server
Real-time conversational AI phone calls for HeartKart vendor ordering.

Bridges Twilio media streams (8 kHz mulaw) ↔ Nova Sonic (16/24 kHz PCM)
via bidirectional WebSocket connections.

Copied from nova_sonic_working_perfectly/ and adapted for AgentCore deployment.
"""

import asyncio
import audioop
import base64
import json
import os
import traceback

from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
import websockets
from dotenv import load_dotenv

from nova_sonic_voice_agent import NovaSonicVendorAgent

# Load environment — try multiple paths depending on where the agent runs
for env_path in ['../../.env', '../.env', '.env']:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break


# ======================================================================
# VENDOR DECISION DETECTION
# ======================================================================

def detect_vendor_decision(conversation_history: list) -> str:
    """
    Analyze conversation history to detect if the vendor said YES or NO.
    Returns 'YES', 'NO', or 'UNKNOWN'.
    """
    if not conversation_history:
        return 'UNKNOWN'

    def _extract_text(msgs, role):
        return ' '.join(
            (msg.get('content', '') if isinstance(msg.get('content'), str)
             else msg['content'][0].get('text', '')
             if isinstance(msg.get('content'), list) and msg['content']
             else '')
            for msg in msgs if msg.get('role') == role
        ).lower()

    vendor_text = _extract_text(conversation_history, 'user')
    ai_text = _extract_text(conversation_history, 'assistant')

    # Check AI closing line (STEP 4 = vendor confirmed)
    if 'purchase order document to your email' in ai_text or 'wonderful' in ai_text:
        print("   📊 Decision: YES (AI reached STEP 4 closing)")
        return 'YES'

    # Check AI polite decline line (STEP 3 NO path)
    if 'thank you for letting me know' in ai_text and "we'll be in touch" in ai_text:
        print("   📊 Decision: NO (AI reached STEP 3 decline path)")
        return 'NO'

    # Keyword matching
    yes_keywords = [
        'yes', 'yeah', 'sure', 'okay', 'ok', 'absolutely', 'definitely',
        'of course', 'no problem', 'we can do that', 'confirmed', 'confirm',
        'approved', 'accepted', 'can fulfil', 'can fulfill', 'we will',
        "we'll do it", 'consider it done', 'right away', 'go ahead',
        'sounds good', 'deal', 'agreed', 'we can', 'will do',
    ]
    no_keywords = [
        'no', 'nope', 'cannot', "can't", 'unable', 'unfortunately',
        'not possible', 'out of stock', 'unavailable', "don't have",
        'do not have', 'sorry', 'regret', 'decline', 'reject',
        'not available', 'can not', "won't be able", 'impossible',
        'not in stock', 'backorder', 'discontinued',
    ]

    yes_count = sum(1 for kw in yes_keywords if kw in vendor_text)
    no_count = sum(1 for kw in no_keywords if kw in vendor_text)
    print(f"   📊 Keyword analysis: YES={yes_count}, NO={no_count}")

    if yes_count > no_count and yes_count > 0:
        return 'YES'
    elif no_count > yes_count and no_count > 0:
        return 'NO'
    return 'UNKNOWN'


# ======================================================================
# AUDIO CONVERSION (mulaw ↔ PCM with state-preserving resampling)
# ======================================================================

conversion_state_in = None
conversion_state_out = None


def mulaw_to_pcm(mulaw_data, sample_rate_in=8000, sample_rate_out=16000):
    """Convert Twilio mulaw (8 kHz) → PCM (16 kHz) for Nova Sonic input."""
    global conversion_state_in
    try:
        if len(mulaw_data) == 0:
            return b''
        pcm_data = audioop.ulaw2lin(mulaw_data, 2)
        if sample_rate_in != sample_rate_out:
            pcm_data, conversion_state_in = audioop.ratecv(
                pcm_data, 2, 1, sample_rate_in, sample_rate_out, conversion_state_in
            )
        return pcm_data
    except Exception as e:
        print(f"⚠️  mulaw_to_pcm error: {e}")
        conversion_state_in = None
        return b''


def pcm_to_mulaw(pcm_data, sample_rate_in=24000, sample_rate_out=8000):
    """Convert Nova Sonic PCM (24 kHz) → mulaw (8 kHz) for Twilio output."""
    global conversion_state_out
    try:
        if len(pcm_data) == 0:
            return b''
        if len(pcm_data) % 2 != 0:
            pcm_data = pcm_data[:-1]
        if sample_rate_in != sample_rate_out:
            pcm_data, conversion_state_out = audioop.ratecv(
                pcm_data, 2, 1, sample_rate_in, sample_rate_out, conversion_state_out
            )
        return audioop.lin2ulaw(pcm_data, 2)
    except Exception as e:
        print(f"⚠️  pcm_to_mulaw error: {e}")
        conversion_state_out = None
        return b''


# ======================================================================
# FLASK APP (Twilio webhooks)
# ======================================================================

app = Flask(__name__)

# Store active call sessions: call_sid → { agent, forward_task }
active_calls = {}


@app.route('/voice', methods=['POST'])
def voice_webhook():
    """
    Twilio webhook — called when the outbound call is answered.
    Returns TwiML that connects the call to the WebSocket media stream.
    """
    call_sid = request.form.get('CallSid')
    from_number = request.form.get('From')
    to_number = request.form.get('To')

    print(f"\n📞 Incoming call:")
    print(f"   Call SID: {call_sid}")
    print(f"   From: {from_number}")
    print(f"   To: {to_number}")

    response = VoiceResponse()

    ngrok_url = os.getenv('NGROK_URL', '').rstrip('/')
    ws_url = ngrok_url.replace('https://', 'wss://').replace('http://', 'ws://')
    connect = Connect()
    stream = Stream(url=f'{ws_url}/media-stream')
    connect.append(stream)
    response.append(connect)

    return str(response)


@app.route('/gather', methods=['POST'])
def gather_webhook():
    """Handle user input after pressing a key."""
    digits = request.form.get('Digits')
    call_sid = request.form.get('CallSid')

    print(f"\n🔢 User pressed: {digits} (Call SID: {call_sid})")

    response = VoiceResponse()

    if digits == '1':
        ngrok_url = os.getenv('NGROK_URL', 'wss://your-ngrok-url.ngrok-free.dev')
        ws_url = ngrok_url.replace('https://', 'wss://').replace('http://', 'ws://')
        connect = Connect()
        stream = Stream(url=f'{ws_url}/media-stream')
        connect.append(stream)
        response.append(connect)
    else:
        response.say("Invalid input. Goodbye!", voice='Polly.Joanna')

    return str(response)


@app.route('/call-status', methods=['POST'])
def call_status():
    """Handle call status updates from Twilio."""
    call_sid = request.form.get('CallSid')
    status = request.form.get('CallStatus')
    print(f"\n📊 Call status update: {call_sid} → {status}")
    return '', 200


# ======================================================================
# WEBSOCKET HANDLER (Twilio ↔ Nova Sonic bridge)
# ======================================================================

async def handle_twilio_stream(websocket):
    """
    Handle WebSocket connection from Twilio.
    Bridges audio bidirectionally between Twilio and Nova Sonic.
    """
    print(f"\n🔌 WebSocket connected")

    call_sid = None
    stream_sid = None
    agent = None

    try:
        async for message in websocket:
            data = json.loads(message)
            event = data.get('event')

            # ----------------------------------------------------------
            # CALL STARTED — create Nova Sonic agent and start session
            # ----------------------------------------------------------
            if event == 'start':
                call_sid = data['start']['callSid']
                stream_sid = data['start']['streamSid']

                print(f"\n📞 Call started:")
                print(f"   Call SID: {call_sid}")
                print(f"   Stream SID: {stream_sid}")

                # Fetch vendor context from Flask backend
                vendor_context = None
                try:
                    import requests
                    api_url = os.getenv("API_URL", "http://localhost:5000")
                    print(f"   🔍 Fetching vendor context from {api_url}/api/get-call-metadata/{call_sid} ...")
                    resp = requests.get(f"{api_url}/api/get-call-metadata/{call_sid}", timeout=5)
                    if resp.status_code == 200:
                        meta = resp.json()
                        if meta.get("success"):
                            vendor_name = meta.get("vendor_name", "the vendor")
                            contact_person = meta.get("contact_person", "there")
                            product_name = meta.get("product_name", "products")
                            quantity = meta.get("quantity", 0) or 0
                            total_amount_usd = meta.get("total_amount", 0) or 0

                            usd_to_inr_rate = float(os.getenv('USD_TO_INR', '89.6'))
                            total_amount_inr = total_amount_usd * usd_to_inr_rate
                            total_amount_str = f"₹{total_amount_inr:,.2f} (Indian Rupees)"

                            delivery_date = meta.get("delivery_date", "as soon as possible")

                            print(f"\n🧩 Vendor context from backend:")
                            print(f"   Vendor: {vendor_name}")
                            print(f"   Contact: {contact_person}")
                            print(f"   Product: {product_name}")
                            print(f"   Quantity: {quantity}")
                            print(f"   Amount: {total_amount_str}")

                            vendor_context = {
                                "vendor_name": vendor_name,
                                "contact_person": contact_person,
                                "purpose": "place a purchase order",
                                "order_details": {
                                    "items": [{"name": product_name, "quantity": quantity}],
                                    "total_amount": total_amount_str,
                                    "delivery_date": delivery_date,
                                },
                            }
                except Exception as e:
                    print(f"⚠️  Error fetching vendor context from backend: {e}")

                if not vendor_context:
                    print("⚠️  Using generic fallback context — backend metadata unavailable")
                    vendor_context = {
                        "vendor_name": "the vendor",
                        "contact_person": "there",
                        "purpose": "place a purchase order",
                        "order_details": {
                            "items": [],
                            "total_amount": "to be confirmed",
                            "delivery_date": "as soon as possible",
                        },
                    }

                # Create Nova Sonic agent and start streaming session
                agent = NovaSonicVendorAgent(vendor_context)
                await agent.start_session()
                print("✅ Nova Sonic session started")

                await agent.start_audio_input()

                # Background task: forward Nova Sonic audio → Twilio
                async def forward_to_twilio():
                    while agent.is_active:
                        try:
                            audio_bytes = await agent.audio_queue.get()
                            if not audio_bytes:
                                continue

                            if len(audio_bytes) % 2 != 0:
                                audio_bytes = audio_bytes + b'\x00'

                            mulaw_audio = pcm_to_mulaw(audio_bytes, 24000, 8000)
                            audio_base64 = base64.b64encode(mulaw_audio).decode('utf-8')

                            msg = {
                                'event': 'media',
                                'streamSid': stream_sid,
                                'media': {'payload': audio_base64},
                            }
                            await websocket.send(json.dumps(msg))
                            await asyncio.sleep(0.001)

                        except asyncio.CancelledError:
                            break
                        except Exception as e:
                            import websockets as _ws
                            if isinstance(e, (_ws.exceptions.ConnectionClosedError,
                                              _ws.exceptions.ConnectionClosedOK)):
                                print("ℹ️  Twilio WebSocket closed – stopping forwarder.")
                                agent.is_active = False
                                break
                            if "no close frame" in str(e):
                                agent.is_active = False
                                break
                            print(f"⚠️  Audio forward error: {e}")
                            continue

                forward_task = asyncio.create_task(forward_to_twilio())
                active_calls[call_sid] = {'agent': agent, 'forward_task': forward_task}

            # ----------------------------------------------------------
            # INCOMING AUDIO — Twilio → Nova Sonic
            # ----------------------------------------------------------
            elif event == 'media':
                if agent and agent.is_active:
                    try:
                        audio_payload = data['media']['payload']
                        mulaw_audio = base64.b64decode(audio_payload)
                        if mulaw_audio:
                            pcm_audio = mulaw_to_pcm(mulaw_audio, 8000, 16000)
                            await agent.send_audio_chunk(pcm_audio)
                    except Exception as e:
                        print(f"⚠️  Incoming audio error: {e}")
                        continue

            # ----------------------------------------------------------
            # CALL ENDED — tear down, detect decision, send transcript
            # ----------------------------------------------------------
            elif event == 'stop':
                print(f"\n📞 Call ended: {call_sid}")

                if call_sid in active_calls:
                    call_data = active_calls[call_sid]
                    agent = call_data['agent']
                    fwd = call_data['forward_task']

                    agent.is_active = False
                    fwd.cancel()

                    await agent.end_audio_input()
                    await agent.end_session()

                    summary = agent.get_conversation_summary()
                    print("\n📊 Call Summary:")
                    print(json.dumps(summary, indent=2))

                    # Detect vendor decision
                    decision = detect_vendor_decision(
                        summary.get('conversation_history', [])
                    )
                    print(f"   🎯 Vendor decision: {decision}")

                    # Send transcript + decision to Flask backend
                    try:
                        import requests
                        api_url = os.getenv('API_URL', 'http://localhost:5000')
                        transcript_data = {
                            'call_sid': call_sid,
                            'conversation_history': summary.get('conversation_history', []),
                            'decision': decision,
                            'transcript': '',
                        }
                        max_retries = 3
                        for retry in range(max_retries):
                            try:
                                resp = requests.post(
                                    f'{api_url}/api/store-transcript',
                                    json=transcript_data,
                                    timeout=10,
                                )
                                if resp.status_code == 200 and resp.json().get('success'):
                                    print(f"✅ Sent transcript to backend for call {call_sid}")
                                    break
                                else:
                                    print(f"⚠️  Backend returned: {resp.status_code}")
                            except Exception:
                                if retry < max_retries - 1:
                                    print(f"⚠️  Retry {retry + 1}/{max_retries}...")
                                    await asyncio.sleep(2)
                    except Exception as e:
                        print(f"⚠️  Failed to send transcript: {e}")
                        traceback.print_exc()

                    del active_calls[call_sid]

                break

    except Exception as e:
        import websockets as _ws
        if isinstance(e, (_ws.exceptions.ConnectionClosedError,
                          _ws.exceptions.ConnectionClosedOK)):
            print("ℹ️  Twilio WebSocket connection closed (no close frame).")
        else:
            print(f"❌ Error in WebSocket handler: {e}")
            traceback.print_exc()
    finally:
        print("🔌 WebSocket disconnected")


# ======================================================================
# WEBSOCKET SERVER STARTUP
# ======================================================================

def start_websocket_server(port=8080):
    """Start WebSocket server for Twilio media-stream connections."""
    print(f"\n🚀 Starting WebSocket server on port {port}...")
    print(f"📡 WebSocket URL: ws://localhost:{port}/media-stream")
    print(f"\n💡 Next steps:")
    print(f"   1. Run ngrok: ngrok http {port}")
    print(f"   2. Set NGROK_URL in your .env")
    print(f"   3. Make a test call")
    print()

    async def serve():
        async with websockets.serve(handle_twilio_stream, "0.0.0.0", port):
            print(f"✅ WebSocket server running!")
            await asyncio.Future()

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        print("\n🛑 WebSocket server stopped by user (Ctrl+C)")


# ======================================================================
# MAIN
# ======================================================================

if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--websocket':
        start_websocket_server(port=8080)
    else:
        print("\n🚀 Starting Flask app for Twilio webhooks...")
        print("📝 Twilio webhook URL: http://your-ngrok-url.ngrok.io/voice")
        print("\n💡 In another terminal, run:")
        print("   python3 nova_sonic_twilio_server.py --websocket")
        print()
        app.run(host='0.0.0.0', port=5001, debug=False)
