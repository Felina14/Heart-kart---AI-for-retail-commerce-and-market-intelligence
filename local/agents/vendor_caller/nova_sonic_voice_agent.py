#!/usr/bin/env python3
"""
Nova Sonic Voice Agent for Vendor Calls
Real-time conversational AI using Amazon Nova Sonic

⚠️  IMPORTANT: Nova Sonic bidirectional streaming API is not yet available
in the public Python SDKs (boto3). This implementation is ready for when
AWS releases the proper SDK support.

Current Status:
- Nova Sonic model is available (amazon.nova-sonic-v1:0) ✅
- Bidirectional streaming API not in boto3 yet ❌
- AWS SDK for Python support coming soon 🔄

For now, use the existing Twilio + Nova Pro text-based vendor caller.
"""

import asyncio
import base64
import json
import uuid
import pyaudio
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment
load_dotenv('../../.env')

# Import Nova Sonic SDK
try:
    from aws_sdk_bedrock_runtime.client import BedrockRuntimeClient
    from aws_sdk_bedrock_runtime.models import (
        InvokeModelWithBidirectionalStreamOperationInput,
        InvokeModelWithBidirectionalStreamInputChunk,
        BidirectionalInputPayloadPart
    )
    from aws_sdk_bedrock_runtime.config import Config
    from smithy_aws_core.identity import StaticCredentialsResolver, AWSCredentialsIdentity
    import boto3  # For credentials
    NOVA_SDK_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Nova Sonic SDK not installed. Error: {e}")
    print("Install with: pip3 install aws-sdk-bedrock-runtime smithy-aws-core")
    exit(1)

# Audio configuration
INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK_SIZE = 1024


class NovaSonicVendorAgent:
    """
    Real-time conversational AI agent using Nova Sonic
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
        
    def _initialize_client(self):
        """Initialize the Bedrock client for Nova Sonic"""
        # Get credentials from boto3 and set as environment variables
        # so EnvironmentCredentialsResolver can find them
        session = boto3.Session()
        credentials = session.get_credentials()
        
        os.environ['AWS_ACCESS_KEY_ID'] = credentials.access_key
        os.environ['AWS_SECRET_ACCESS_KEY'] = credentials.secret_key
        if hasattr(credentials, 'token') and credentials.token:
            os.environ['AWS_SESSION_TOKEN'] = credentials.token
        
        # Use EnvironmentCredentialsResolver
        from smithy_aws_core.identity import EnvironmentCredentialsResolver
        
        config = Config(
            endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
            region=self.region,
            aws_credentials_identity_resolver=EnvironmentCredentialsResolver()
        )
        self.client = BedrockRuntimeClient(config=config)
    
    async def send_event(self, event_json):
        """Send an event to the bidirectional stream"""
        event = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=event_json.encode('utf-8'))
        )
        await self.stream.input_stream.send(event)
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for the vendor call"""
        vendor_name = self.vendor_context.get('vendor_name', 'the vendor')
        contact_person = self.vendor_context.get('contact_person', 'there')
        purpose = self.vendor_context.get('purpose', 'place an order')

        # Log vendor context so we can verify the correct name is being used
        try:
            print("\n🧩 Nova Sonic vendor context:")
            print(json.dumps(self.vendor_context, indent=2))
        except Exception:
            pass

        # Build greeting based on whether we have a contact person name
        if contact_person and contact_person not in ('there', 'Purchasing Manager', 'the vendor representative'):
            greeting_line = f"Hi there, this is Alex from HeartKart. I'm calling to speak with {contact_person} from {vendor_name}."
        else:
            greeting_line = f"Hi there, this is Alex from HeartKart. I'm calling {vendor_name} regarding a purchase order."

        # Build order details summary
        order_details = self.vendor_context.get('order_details', {})
        items = order_details.get('items', [])
        total_amount = order_details.get('total_amount', 'to be confirmed')
        delivery_date = order_details.get('delivery_date', 'as soon as possible')

        if items:
            if isinstance(items[0], dict):
                items_summary = ', '.join(
                    f"{item.get('quantity', '')} units of {item.get('name', 'item')}"
                    for item in items
                )
            else:
                items_summary = ', '.join(str(i) for i in items)
        else:
            items_summary = 'the requested items'

        prompt = f"""You are Alex, a friendly and professional inventory manager at HeartKart,
a Valentine's Day retail company. You're calling {vendor_name}.

Your personality:
- Warm, friendly, and professional
- Keep responses SHORT (1-2 sentences max)
- Sound human, not robotic

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
- NEVER say or read out internal IDs like PO numbers, order IDs, or system reference codes.
- When talking about prices or amounts, ALWAYS speak in rupees and NEVER say "dollars" or use the "$" symbol.
- If you mention totals, say them as approximate rupee amounts (e.g., "about ten thousand rupees") rather than exact cents.
- NEVER use abbreviations like "ASAP". Always say the full form, for example "as soon as possible".

**YOUR FIRST ASSISTANT RESPONSE IN THIS CONVERSATION MUST BE EXACTLY:**
"{greeting_line}"

**REMEMBER:**
- You MUST say "{vendor_name}" in your first sentence.
- NEVER skip stating the order details (Step 2).
- NEVER use abbreviations — always speak in full words.
- All currency is in rupees – never say "dollars".
- This is a PHONE CALL. Keep it conversational and brief!"""

        return prompt
    
    async def start_session(self):
        """Start a new Nova Sonic session"""
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
                        "topP": 0.8,
                        "temperature": 0.1
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
                    "textOutputConfiguration": {
                        "mediaType": "text/plain"
                    },
                    "audioOutputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": OUTPUT_SAMPLE_RATE,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "voiceId": "tiffany",  # Feminine voice (US English)
                        "encoding": "base64",
                        "audioType": "SPEECH"
                    }
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
                    "textInputConfiguration": {
                        "mediaType": "text/plain"
                    }
                }
            }
        }
        await self.send_event(json.dumps(text_content_start))
        
        text_input = {
            "event": {
                "textInput": {
                    "promptName": self.prompt_name,
                    "contentName": self.content_name,
                    "content": system_prompt
                }
            }
        }
        await self.send_event(json.dumps(text_input))
        
        text_content_end = {
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": self.content_name
                }
            }
        }
        await self.send_event(json.dumps(text_content_end))
        
        # Start processing responses
        self.response = asyncio.create_task(self._process_responses())
        
        print("✅ Nova Sonic session started!")
    
    async def start_audio_input(self):
        """Start audio input stream"""
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
                        "encoding": "base64"
                    }
                }
            }
        }
        await self.send_event(json.dumps(audio_content_start))
    
    async def send_audio_chunk(self, audio_bytes):
        """Send audio chunk to Nova Sonic"""
        if not self.is_active:
            return
        
        blob = base64.b64encode(audio_bytes)
        audio_event = {
            "event": {
                "audioInput": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                    "content": blob.decode('utf-8')
                }
            }
        }
        await self.send_event(json.dumps(audio_event))
    
    async def end_audio_input(self):
        """End audio input stream"""
        audio_content_end = {
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name
                }
            }
        }
        await self.send_event(json.dumps(audio_content_end))
    
    async def _process_responses(self):
        """Process responses from Nova Sonic"""
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
                    msg = str(inner_e)
                    if any(k in msg for k in ["Timed out", "closed", "completed", "cancelled"]):
                        print(f"   Nova Sonic stream closed: {msg}")
                    else:
                        print(f"⚠️  Response event error: {inner_e}")
                    break
        except asyncio.CancelledError:
            print("   Response processing cancelled")
        except Exception as e:
            print(f"Error processing responses: {e}")
        finally:
            self.is_active = False
            await self.audio_queue.put(None)
            print("   Response processing exited")
    
    async def _handle_event(self, event_data):
        """Handle different event types from Nova Sonic"""
        if 'event' not in event_data:
            return
        
        event = event_data['event']
        
        # Handle content start event
        if 'contentStart' in event:
            content_start = event['contentStart']
            self.current_role = content_start.get('role', 'UNKNOWN')
            
            # Check for speculative content
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
                        'timestamp': datetime.now().isoformat()
                    })
                elif self.current_role == "USER":
                    print(f"👤 Vendor: {text}")
                    self.conversation_history.append({
                        'role': 'user',
                        'content': text,
                        'timestamp': datetime.now().isoformat()
                    })
        
        # Handle audio output (AI voice)
        elif 'audioOutput' in event:
            audio_base64 = event['audioOutput'].get('content', '')
            if audio_base64:
                audio_bytes = base64.b64decode(audio_base64)
                await self.audio_queue.put(audio_bytes)
    
    async def play_audio(self):
        """Play audio responses from Nova Sonic"""
        p = pyaudio.PyAudio()
        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=OUTPUT_SAMPLE_RATE,
            output=True
        )
        
        try:
            while self.is_active:
                audio_data = await self.audio_queue.get()
                stream.write(audio_data)
        except Exception as e:
            print(f"Error playing audio: {e}")
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()
    
    async def capture_audio(self, duration_seconds=30):
        """Capture audio from microphone and send to Nova Sonic"""
        p = pyaudio.PyAudio()
        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=INPUT_SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE
        )
        
        print("🎤 Starting audio capture. Speak into your microphone...")
        print(f"⏱️  Will capture for {duration_seconds} seconds (or press Ctrl+C to stop early)")
        
        await self.start_audio_input()
        
        try:
            start_time = asyncio.get_event_loop().time()
            while self.is_active:
                # Check if duration exceeded
                if asyncio.get_event_loop().time() - start_time > duration_seconds:
                    print(f"\n⏰ {duration_seconds} seconds elapsed, stopping capture...")
                    break
                
                audio_data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                await self.send_audio_chunk(audio_data)
                await asyncio.sleep(0.01)
        except KeyboardInterrupt:
            print("\n⏹️  Capture stopped by user")
        except Exception as e:
            print(f"Error capturing audio: {e}")
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()
            print("🔇 Audio capture stopped.")
            await self.end_audio_input()
    
    async def end_session(self):
        """End the Nova Sonic session cleanly.

        Let the CRT drain its HTTP/2 streams naturally instead of
        force-cancelling, which corrupts the connection pool.
        """
        if not self.is_active and self.client is None:
            return  # already cleaned up
        self.is_active = False

        try:
            prompt_end = {
                "event": {"promptEnd": {"promptName": self.prompt_name}}
            }
            await self.send_event(json.dumps(prompt_end))

            session_end = {"event": {"sessionEnd": {}}}
            await self.send_event(json.dumps(session_end))
        except Exception as e:
            print(f"   ⚠️  Error sending close events: {e}")

        try:
            if self.stream:
                await self.stream.input_stream.close()
        except Exception as e:
            print(f"   ⚠️  Error closing input stream: {e}")

        # Wait for response task to exit naturally (not via cancel)
        if self.response and not self.response.done():
            try:
                await asyncio.wait_for(asyncio.shield(self.response), timeout=5.0)
            except asyncio.TimeoutError:
                self.response.cancel()
                try:
                    await self.response
                except (asyncio.CancelledError, Exception):
                    pass
            except Exception:
                pass

        await asyncio.sleep(0.3)
        self.client = None
        self.stream = None
        print("📞 Session ended")
    
    def get_conversation_summary(self):
        """Get summary of the conversation"""
        return {
            'vendor_name': self.vendor_context.get('vendor_name'),
            'purpose': self.vendor_context.get('purpose'),
            'conversation_length': len(self.conversation_history),
            'conversation_history': self.conversation_history,
            'timestamp': datetime.now().isoformat()
        }


# Test function
async def test_nova_sonic_interactive():
    """Test Nova Sonic with real microphone and speaker"""
    print("=" * 70)
    print("🤖 NOVA SONIC VOICE AGENT - Interactive Test")
    print("=" * 70)
    
    # Create vendor call context
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
    
    # Create agent
    agent = NovaSonicVendorAgent(vendor_context)
    
    try:
        # Start session
        await agent.start_session()
        
        print("\n📞 Session active! Nova Sonic is ready for a real conversation.")
        print("🎤 Make sure your microphone and speakers are working.")
        print("💬 The AI will start the conversation, then you can respond.\n")
        
        # Start audio playback task
        playback_task = asyncio.create_task(agent.play_audio())
        
        # Start audio capture task (30 seconds)
        capture_task = asyncio.create_task(agent.capture_audio(duration_seconds=30))
        
        # Wait for capture to complete
        await capture_task
        
        # Give time for final audio playback
        await asyncio.sleep(2)
        
        # End session
        agent.is_active = False
        
        # Cancel playback task
        if not playback_task.done():
            playback_task.cancel()
            try:
                await playback_task
            except asyncio.CancelledError:
                pass
        
        # Cancel response task
        if agent.response and not agent.response.done():
            agent.response.cancel()
            try:
                await agent.response
            except asyncio.CancelledError:
                pass
        
        await agent.end_session()
        
        # Get summary
        summary = agent.get_conversation_summary()
        print("\n" + "=" * 70)
        print("📊 CALL SUMMARY")
        print("=" * 70)
        print(json.dumps(summary, indent=2))
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


async def test_nova_sonic_simple():
    """Simple test without audio I/O - just verify connection"""
    print("=" * 70)
    print("🤖 NOVA SONIC VOICE AGENT - Connection Test")
    print("=" * 70)
    
    vendor_context = {
        'vendor_name': 'Test Vendor',
        'contact_person': 'Test Contact',
        'purpose': 'test connection'
    }
    
    agent = NovaSonicVendorAgent(vendor_context)
    
    try:
        print("\n🔌 Testing connection to Nova Sonic...")
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
    print()
    
    # Check if SDK is installed
    try:
        from aws_sdk_bedrock_runtime.client import BedrockRuntimeClient
        print("✅ Nova Sonic SDK installed")
    except ImportError:
        print("❌ Nova Sonic SDK not installed")
        print("\nInstall with:")
        print("pip install aws-sdk-bedrock-runtime smithy-aws-core pyaudio")
        exit(1)
    
    # Check for test mode argument
    if len(sys.argv) > 1 and sys.argv[1] == '--interactive':
        print("\n🎤 Running INTERACTIVE test (with microphone and speakers)")
        asyncio.run(test_nova_sonic_interactive())
    else:
        print("\n🔌 Running SIMPLE connection test (no audio I/O)")
        print("💡 Use --interactive flag for full audio test")
        asyncio.run(test_nova_sonic_simple())
