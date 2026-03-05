#!/usr/bin/env python3
"""
Nova Sonic Voice Agent for Vendor Calls
Real-time conversational AI using Amazon Nova Sonic bidirectional streaming.

Copied from nova_sonic_working_perfectly/ and adapted for AgentCore deployment.

Current Status:
- Nova Sonic model is available (amazon.nova-sonic-v1:0) ✅
- Bidirectional streaming via aws-sdk-bedrock-runtime ✅
- Twilio WebSocket integration ✅
"""

import asyncio
import base64
import json
import traceback
import uuid
import os
from datetime import datetime

import boto3

# Import Nova Sonic SDK
try:
    from aws_sdk_bedrock_runtime.client import BedrockRuntimeClient
    from aws_sdk_bedrock_runtime.models import (
        InvokeModelWithBidirectionalStreamOperationInput,
        InvokeModelWithBidirectionalStreamInputChunk,
        BidirectionalInputPayloadPart,
    )
    from aws_sdk_bedrock_runtime.config import Config
    from smithy_aws_core.identity import EnvironmentCredentialsResolver
    NOVA_SDK_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Nova Sonic SDK not installed. Error: {e}")
    print("Install with: pip3 install aws-sdk-bedrock-runtime smithy-aws-core")
    NOVA_SDK_AVAILABLE = False

# Audio configuration
INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK_SIZE = 1024


class NovaSonicVendorAgent:
    """
    Real-time conversational AI agent using Nova Sonic bidirectional streaming.

    Creates a persistent bidirectional stream to Amazon Nova Sonic and sends /
    receives audio in real time.  The agent follows a strict 4-step call script
    for placing purchase orders with vendors.
    """

    def __init__(self, vendor_context: dict, model_id='amazon.nova-sonic-v1:0', region='us-east-1'):
        self.model_id = model_id
        self.region = region
        self.vendor_context = vendor_context
        self.client = None
        self.stream = None
        self.response = None
        self.is_active = False

        # Unique IDs for tracking
        self.prompt_name = str(uuid.uuid4())
        self.content_name = str(uuid.uuid4())
        self.audio_content_name = str(uuid.uuid4())

        # Audio queue for playback
        self.audio_queue = asyncio.Queue()

        # Conversation tracking
        self.conversation_history = []
        self.current_role = None
        self.display_assistant_text = True

    # ------------------------------------------------------------------
    # CLIENT INITIALISATION
    # ------------------------------------------------------------------

    def _initialize_client(self):
        """Initialize the Bedrock client for Nova Sonic."""
        session = boto3.Session()
        credentials = session.get_credentials()

        os.environ['AWS_ACCESS_KEY_ID'] = credentials.access_key
        os.environ['AWS_SECRET_ACCESS_KEY'] = credentials.secret_key
        if hasattr(credentials, 'token') and credentials.token:
            os.environ['AWS_SESSION_TOKEN'] = credentials.token

        config = Config(
            endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
            region=self.region,
            aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
        )
        self.client = BedrockRuntimeClient(config=config)

    # ------------------------------------------------------------------
    # STREAM HELPERS
    # ------------------------------------------------------------------

    async def send_event(self, event_json):
        """Send an event to the bidirectional stream."""
        event = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=event_json.encode('utf-8'))
        )
        await self.stream.input_stream.send(event)

    # ------------------------------------------------------------------
    # SYSTEM PROMPT (4-step call script)
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        """Build the system prompt for the vendor call."""
        vendor_name = self.vendor_context.get('vendor_name', 'the vendor')
        contact_person = self.vendor_context.get('contact_person', 'there')
        order_details = self.vendor_context.get('order_details', {})
        items = order_details.get('items', [])
        total_amount = order_details.get('total_amount', 'to be confirmed')
        delivery_date = order_details.get('delivery_date', 'as soon as possible')

        if items:
            items_summary = ', '.join(
                f"{item.get('quantity', '')} units of {item.get('name', 'item')}"
                for item in items
            )
        else:
            items_summary = 'the requested items'

        # Build greeting based on whether we have a contact person name
        if contact_person and contact_person not in ('there', 'Purchasing Manager', 'the vendor representative'):
            greeting_line = f"Hello, this is Priya calling from HeartKart. I'm calling to speak with {contact_person} from {vendor_name}."
        else:
            greeting_line = f"Hello, this is Priya calling from HeartKart. I'm calling {vendor_name} regarding a purchase order."

        prompt = f"""You are Priya, an inventory manager at HeartKart calling {vendor_name}.

STRICT CALL SCRIPT — you MUST follow these steps in EXACT order. NEVER skip a step.

STEP 1 — GREET (1 sentence):
"{greeting_line}"
Then WAIT for the vendor to respond. Their response here is just them confirming they are listening — it is NOT a response to any order. Do NOT treat "yes", "speaking", "tell me", "go ahead" etc. as order confirmation at this stage.

STEP 2 — STATE THE ORDER (MANDATORY — you MUST always say this, no matter what):
After the vendor responds to your greeting (e.g. "yes speaking", "tell me", "go ahead"), you MUST state the order details. Say:
"I'd like to place a purchase order for {items_summary}, totalling {total_amount}, with delivery needed by {delivery_date}. Can you fulfil this order?"
This step is MANDATORY. You cannot skip it. You must say the order details before anything else.

STEP 3 — HANDLE RESPONSE TO THE ORDER (only after you have stated the order in Step 2):
• If vendor says YES / confirms / agrees to the ORDER → go to STEP 4.
• If vendor says NO / cannot / unavailable → say "I understand, thank you for letting me know. We'll be in touch." and end the call.
• If vendor asks a clarifying question → answer briefly (1 sentence) then re-ask if they can fulfil.

STEP 4 — CLOSE (only after vendor has confirmed the ORDER from Step 2):
Say exactly: "Wonderful! We'll send the purchase order document to your email shortly. Thank you so much, and have a great day!"
Then the call is complete — do not say anything further.

CRITICAL RULES:
- You MUST complete Step 1, then Step 2, then Step 3, then Step 4 in that exact order. NEVER skip Step 2.
- The vendor's first response after your greeting (Step 1) is NEVER an order confirmation — it is simply them acknowledging the call. You MUST then proceed to Step 2 and state the order.
- Only treat a vendor's "yes" as order confirmation AFTER you have stated the order details in Step 2.
- Keep every response to 1-2 sentences maximum.
- Do not read out PO numbers or long reference codes aloud.
- NEVER use abbreviations like "ASAP". Always say the full form, for example "as soon as possible".
- Sound warm and human, not robotic."""

        return prompt

    # ------------------------------------------------------------------
    # SESSION MANAGEMENT
    # ------------------------------------------------------------------

    async def start_session(self):
        """Start a new Nova Sonic bidirectional streaming session."""
        if not self.client:
            self._initialize_client()

        print("🎙️ Starting Nova Sonic session...")

        # Initialize the bidirectional stream
        self.stream = await self.client.invoke_model_with_bidirectional_stream(
            InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)
        )
        self.is_active = True

        # 1. Send session start event
        session_start = {
            "event": {
                "sessionStart": {
                    "inferenceConfiguration": {
                        "maxTokens": 512,
                        "topP": 0.9,
                        "temperature": 0.7,
                    }
                }
            }
        }
        await self.send_event(json.dumps(session_start))

        # 2. Send prompt start event
        prompt_start = {
            "event": {
                "promptStart": {
                    "promptName": self.prompt_name,
                    "textOutputConfiguration": {"mediaType": "text/plain"},
                    "audioOutputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": OUTPUT_SAMPLE_RATE,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "voiceId": "tiffany",
                        "encoding": "base64",
                        "audioType": "SPEECH",
                    },
                }
            }
        }
        await self.send_event(json.dumps(prompt_start))

        # 3. Send system prompt
        system_prompt = self._build_system_prompt()

        text_content_start = {
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": self.content_name,
                    "type": "TEXT",
                    "interactive": True,
                    "role": "SYSTEM",
                    "textInputConfiguration": {"mediaType": "text/plain"},
                }
            }
        }
        await self.send_event(json.dumps(text_content_start))

        text_input = {
            "event": {
                "textInput": {
                    "promptName": self.prompt_name,
                    "contentName": self.content_name,
                    "content": system_prompt,
                }
            }
        }
        await self.send_event(json.dumps(text_input))

        text_content_end = {
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": self.content_name,
                }
            }
        }
        await self.send_event(json.dumps(text_content_end))

        # Start processing responses
        self.response = asyncio.create_task(self._process_responses())

        # Send initial text trigger so Nova Sonic speaks first without waiting for audio
        await self._send_initial_greeting()

        print("✅ Nova Sonic session started!")

    # ------------------------------------------------------------------
    # INITIAL GREETING TRIGGER
    # ------------------------------------------------------------------

    async def _send_initial_greeting(self):
        """Send a text trigger so Nova Sonic speaks first (Step 1 of call script)."""
        greeting_content_name = str(uuid.uuid4())

        text_content_start = {
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": greeting_content_name,
                    "type": "TEXT",
                    "interactive": True,
                    "role": "USER",
                    "textInputConfiguration": {"mediaType": "text/plain"},
                }
            }
        }
        await self.send_event(json.dumps(text_content_start))

        text_input = {
            "event": {
                "textInput": {
                    "promptName": self.prompt_name,
                    "contentName": greeting_content_name,
                    "content": "Start the call by greeting the vendor.",
                }
            }
        }
        await self.send_event(json.dumps(text_input))

        text_content_end = {
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": greeting_content_name,
                }
            }
        }
        await self.send_event(json.dumps(text_content_end))
        print("   ✅ Initial greeting trigger sent")

    # ------------------------------------------------------------------
    # AUDIO INPUT
    # ------------------------------------------------------------------

    async def start_audio_input(self):
        """Start audio input stream."""
        audio_content_start = {
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                    "type": "AUDIO",
                    "interactive": True,
                    "role": "USER",
                    "audioInputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": INPUT_SAMPLE_RATE,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "audioType": "SPEECH",
                        "encoding": "base64",
                    },
                }
            }
        }
        await self.send_event(json.dumps(audio_content_start))

    async def send_audio_chunk(self, audio_bytes):
        """Send audio chunk to Nova Sonic."""
        if not self.is_active:
            return

        blob = base64.b64encode(audio_bytes)
        audio_event = {
            "event": {
                "audioInput": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                    "content": blob.decode('utf-8'),
                }
            }
        }
        await self.send_event(json.dumps(audio_event))

    async def end_audio_input(self):
        """End audio input stream."""
        audio_content_end = {
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                }
            }
        }
        await self.send_event(json.dumps(audio_content_end))

    # ------------------------------------------------------------------
    # RESPONSE PROCESSING
    # ------------------------------------------------------------------

    async def _process_responses(self):
        """Process responses from Nova Sonic."""
        try:
            while self.is_active:
                try:
                    output = await self.stream.await_output()
                    result = await output[1].receive()

                    if result.value and result.value.bytes_:
                        response_data = result.value.bytes_.decode('utf-8')
                        json_data = json.loads(response_data)

                        if 'event' in json_data:
                            await self._handle_event(json_data)
                except StopAsyncIteration:
                    print("   Nova Sonic stream ended (StopAsyncIteration)")
                    break
                except Exception as inner_e:
                    if not self.is_active:
                        break  # Expected during clean shutdown
                    err_str = str(inner_e).lower()
                    if 'closed' in err_str or 'completed' in err_str or 'cancelled' in err_str:
                        print(f"   Nova Sonic stream closed: {inner_e}")
                        break
                    print(f"⚠️  Response event error: {inner_e}")
                    break
        except asyncio.CancelledError:
            print("   Response processing cancelled")
        except Exception as e:
            print(f"ERROR processing Nova Sonic responses: {e}")
            traceback.print_exc()
        finally:
            self.is_active = False
            # Put sentinel to unblock _forward_audio loop
            await self.audio_queue.put(None)
            print("   Response processing exited")

    async def _handle_event(self, event_data):
        """Handle different event types from Nova Sonic."""
        if 'event' not in event_data:
            return

        event = event_data['event']

        # Handle content start event
        if 'contentStart' in event:
            content_start = event['contentStart']
            self.current_role = content_start.get('role', 'UNKNOWN')

            if 'additionalModelFields' in content_start:
                additional_fields = json.loads(content_start['additionalModelFields'])
                if additional_fields.get('generationStage') == 'SPECULATIVE':
                    self.display_assistant_text = True
                else:
                    self.display_assistant_text = False

        # Handle text output (transcription)
        elif 'textOutput' in event:
            text = event['textOutput'].get('content', '')
            if text:
                if self.current_role == "ASSISTANT" and getattr(self, 'display_assistant_text', True):
                    print(f"🤖 AI: {text}")
                    self.conversation_history.append({
                        'role': 'assistant',
                        'content': text,
                        'timestamp': datetime.now().isoformat(),
                    })
                elif self.current_role == "USER":
                    print(f"👤 Vendor: {text}")
                    self.conversation_history.append({
                        'role': 'user',
                        'content': text,
                        'timestamp': datetime.now().isoformat(),
                    })

        # Handle audio output (AI voice)
        elif 'audioOutput' in event:
            audio_base64 = event['audioOutput'].get('content', '')
            if audio_base64:
                audio_bytes = base64.b64decode(audio_base64)
                await self.audio_queue.put(audio_bytes)

    # ------------------------------------------------------------------
    # SESSION TEARDOWN
    # ------------------------------------------------------------------

    async def end_session(self):
        """End the Nova Sonic session cleanly.

        Key: let the CRT drain its HTTP/2 streams naturally instead of
        force-cancelling, which corrupts the global connection pool and
        causes all subsequent sessions to silently produce no output.
        """
        if not self.is_active and self.client is None:
            return  # already cleaned up
        self.is_active = False

        # 1. Send close events so Nova Sonic knows we're done
        try:
            prompt_end = {
                "event": {"promptEnd": {"promptName": self.prompt_name}}
            }
            await self.send_event(json.dumps(prompt_end))

            session_end = {"event": {"sessionEnd": {}}}
            await self.send_event(json.dumps(session_end))
        except Exception as e:
            print(f"   ⚠️  Error sending close events: {e}")

        # 2. Close the input stream — this tells CRT we're done writing
        try:
            if self.stream:
                await self.stream.input_stream.close()
        except Exception as e:
            print(f"   ⚠️  Error closing input stream: {e}")

        # 3. Wait for _process_responses to exit NATURALLY (not via cancel).
        #    The stream close above causes await_output() to error/return,
        #    which breaks the loop without corrupting CRT state.
        if self.response and not self.response.done():
            try:
                await asyncio.wait_for(asyncio.shield(self.response), timeout=5.0)
            except asyncio.TimeoutError:
                print("   ⚠️  Response task did not exit in 5s — force cancelling")
                self.response.cancel()
                try:
                    await self.response
                except (asyncio.CancelledError, Exception):
                    pass
            except Exception:
                pass

        # 4. Give CRT a moment to finish HTTP/2 cleanup
        await asyncio.sleep(0.3)

        # 5. Destroy references
        self.client = None
        self.stream = None
        print("📞 Session ended")

    # ------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------

    def get_conversation_summary(self):
        """Get summary of the conversation."""
        return {
            'vendor_name': self.vendor_context.get('vendor_name'),
            'purpose': self.vendor_context.get('purpose'),
            'conversation_length': len(self.conversation_history),
            'conversation_history': self.conversation_history,
            'timestamp': datetime.now().isoformat(),
        }


# ======================================================================
# STANDALONE TEST (microphone + speaker)
# ======================================================================

async def test_nova_sonic_interactive():
    """Test Nova Sonic with real microphone and speaker."""
    try:
        import pyaudio  # Only needed for local mic/speaker tests
    except ImportError:
        print("❌ pyaudio not installed — needed for interactive test only")
        return

    print("=" * 70)
    print("🤖 NOVA SONIC VOICE AGENT — Interactive Test")
    print("=" * 70)

    vendor_context = {
        'vendor_name': 'Valentine Gifts Wholesale',
        'contact_person': 'Priya',
        'purpose': 'place a purchase order',
        'order_details': {
            'items': [
                {'name': 'Heart-Shaped Gift Box', 'quantity': 100},
                {'name': 'Rose Bouquet Set', 'quantity': 50},
            ],
            'total_amount': '₹1,12,000.00 (Indian Rupees)',
            'delivery_date': 'February 10th',
        },
    }

    agent = NovaSonicVendorAgent(vendor_context)

    try:
        await agent.start_session()

        FORMAT = pyaudio.paInt16

        # Audio playback task
        async def play_audio():
            p = pyaudio.PyAudio()
            stream = p.open(format=FORMAT, channels=CHANNELS, rate=OUTPUT_SAMPLE_RATE, output=True)
            try:
                while agent.is_active:
                    audio_data = await agent.audio_queue.get()
                    stream.write(audio_data)
            except Exception:
                pass
            finally:
                stream.stop_stream()
                stream.close()
                p.terminate()

        # Audio capture task
        async def capture_audio(duration=30):
            p = pyaudio.PyAudio()
            stream = p.open(format=FORMAT, channels=CHANNELS, rate=INPUT_SAMPLE_RATE,
                            input=True, frames_per_buffer=CHUNK_SIZE)
            await agent.start_audio_input()
            try:
                start = asyncio.get_event_loop().time()
                while agent.is_active and (asyncio.get_event_loop().time() - start) < duration:
                    audio_data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                    await agent.send_audio_chunk(audio_data)
                    await asyncio.sleep(0.01)
            except KeyboardInterrupt:
                pass
            finally:
                stream.stop_stream()
                stream.close()
                p.terminate()
                await agent.end_audio_input()

        playback_task = asyncio.create_task(play_audio())
        capture_task = asyncio.create_task(capture_audio(30))
        await capture_task
        await asyncio.sleep(2)

        agent.is_active = False
        if not playback_task.done():
            playback_task.cancel()
        if agent.response and not agent.response.done():
            agent.response.cancel()

        await agent.end_session()
        print(json.dumps(agent.get_conversation_summary(), indent=2))

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


async def test_nova_sonic_simple():
    """Simple connection test (no audio I/O)."""
    print("=" * 70)
    print("🤖 NOVA SONIC VOICE AGENT — Connection Test")
    print("=" * 70)

    agent = NovaSonicVendorAgent({
        'vendor_name': 'Test Vendor',
        'contact_person': 'Test Contact',
        'purpose': 'test connection',
    })

    try:
        await agent.start_session()
        print("✅ Connection successful!")
        await asyncio.sleep(2)
        await agent.end_session()
        print("✅ Session ended cleanly")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    import sys
    print("🚀 Testing Nova Sonic Voice Agent...")
    if len(sys.argv) > 1 and sys.argv[1] == '--interactive':
        asyncio.run(test_nova_sonic_interactive())
    else:
        asyncio.run(test_nova_sonic_simple())
