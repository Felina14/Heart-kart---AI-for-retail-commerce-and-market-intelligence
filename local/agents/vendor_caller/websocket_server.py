#!/usr/bin/env python3
"""
WebSocket Server for Real-Time Conversational AI
Handles Twilio Media Streams for live audio processing
"""

import asyncio
import websockets
import json
import base64
import boto3
from conversational_ai_agent import ConversationalAIAgent

# AWS clients
transcribe_client = boto3.client('transcribestreaming', region_name='us-east-1')

class TwilioMediaStreamHandler:
    """Handles Twilio Media Stream WebSocket connection"""
    
    def __init__(self, websocket, call_context):
        self.websocket = websocket
        self.call_context = call_context
        self.ai_agent = ConversationalAIAgent(call_context)
        self.audio_buffer = []
        self.is_speaking = False
        self.stream_sid = None
        
    async def handle_connection(self):
        """Main handler for WebSocket connection"""
        print(f"📞 New call connected")
        
        # Send opening message
        await self.speak(self.ai_agent.get_opening_message())
        
        try:
            async for message in self.websocket:
                await self.process_message(message)
        except websockets.exceptions.ConnectionClosed:
            print("📞 Call ended")
            
            # Get call summary
            summary = self.ai_agent.get_call_summary()
            print(f"📊 Call Summary: {json.dumps(summary, indent=2)}")
    
    async def process_message(self, message):
        """Process incoming WebSocket message from Twilio"""
        try:
            data = json.loads(message)
            event_type = data.get('event')
            
            if event_type == 'start':
                await self.handle_start(data)
            elif event_type == 'media':
                await self.handle_media(data)
            elif event_type == 'stop':
                await self.handle_stop(data)
                
        except Exception as e:
            print(f"Error processing message: {e}")
    
    async def handle_start(self, data):
        """Handle stream start event"""
        self.stream_sid = data['start']['streamSid']
        call_sid = data['start']['callSid']
        print(f"🎙️ Stream started: {self.stream_sid}")
        print(f"📞 Call SID: {call_sid}")
    
    async def handle_media(self, data):
        """Handle incoming audio data"""
        if self.is_speaking:
            return  # Don't process while AI is speaking
        
        # Get audio payload
        payload = data['media']['payload']
        
        # Decode base64 audio (mulaw format)
        audio_bytes = base64.b64decode(payload)
        
        # Buffer audio
        self.audio_buffer.append(audio_bytes)
        
        # Process when we have enough audio (e.g., 1 second)
        if len(self.audio_buffer) >= 50:  # ~1 second at 20ms chunks
            await self.process_audio_buffer()
    
    async def process_audio_buffer(self):
        """Process buffered audio through speech-to-text"""
        if not self.audio_buffer:
            return
        
        # Combine audio chunks
        audio_data = b''.join(self.audio_buffer)
        self.audio_buffer = []
        
        # Transcribe audio
        text = await self.transcribe_audio(audio_data)
        
        if text and len(text.strip()) > 0:
            print(f"👤 Vendor said: {text}")
            
            # Generate AI response
            ai_response = await self.ai_agent.process_speech(text)
            print(f"🤖 AI responds: {ai_response}")
            
            # Speak the response
            await self.speak(ai_response)
    
    async def transcribe_audio(self, audio_data: bytes) -> str:
        """
        Transcribe audio using Amazon Transcribe
        Note: This is simplified. Real implementation needs streaming transcribe.
        """
        try:
            # For now, return empty (would use AWS Transcribe Streaming API)
            # Real implementation would use:
            # - Start transcription stream
            # - Send audio chunks
            # - Receive partial/final transcripts
            # - Return when speech ends
            
            # Placeholder - in production, use AWS Transcribe Streaming
            return ""
            
        except Exception as e:
            print(f"Transcription error: {e}")
            return ""
    
    async def speak(self, text: str):
        """Convert text to speech and stream to call"""
        self.is_speaking = True
        
        try:
            # Generate speech audio
            audio_bytes = await self.ai_agent.text_to_speech(text)
            
            # Convert to base64 mulaw for Twilio
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
            
            # Send audio to Twilio
            media_message = {
                'event': 'media',
                'streamSid': self.stream_sid,
                'media': {
                    'payload': audio_base64
                }
            }
            
            await self.websocket.send(json.dumps(media_message))
            
            # Mark message as sent
            mark_message = {
                'event': 'mark',
                'streamSid': self.stream_sid,
                'mark': {
                    'name': 'audio_sent'
                }
            }
            
            await self.websocket.send(json.dumps(mark_message))
            
        except Exception as e:
            print(f"Error speaking: {e}")
        finally:
            self.is_speaking = False
    
    async def handle_stop(self, data):
        """Handle stream stop event"""
        print(f"🛑 Stream stopped")


async def handle_websocket(websocket, path):
    """Handle incoming WebSocket connection from Twilio"""
    print(f"🔌 WebSocket connected: {path}")
    
    # Get call context (would come from database in production)
    call_context = {
        'vendor_name': 'Holiday Decor Wholesale',
        'contact_person': 'Sarah',
        'purpose': 'place_order',
        'order_details': {
            'items': ['Red Ornaments', 'Gold Garland'],
            'total_amount': 1250.00,
            'delivery_date': 'November 25th'
        }
    }
    
    handler = TwilioMediaStreamHandler(websocket, call_context)
    await handler.handle_connection()


async def start_server(host='0.0.0.0', port=8080):
    """Start WebSocket server"""
    print("=" * 70)
    print("🚀 Starting Conversational AI WebSocket Server")
    print("=" * 70)
    print(f"📡 Listening on ws://{host}:{port}")
    print(f"🔗 Twilio should connect to: ws://YOUR_PUBLIC_IP:{port}/media")
    print()
    print("💡 Make sure to:")
    print("   1. Expose this port publicly (use ngrok or deploy to cloud)")
    print("   2. Update Twilio to use this WebSocket URL")
    print("   3. Have AWS credentials configured")
    print()
    print("Waiting for connections...")
    print("=" * 70)
    
    async with websockets.serve(handle_websocket, host, port):
        await asyncio.Future()  # Run forever


if __name__ == '__main__':
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        print("\n👋 Server stopped")
