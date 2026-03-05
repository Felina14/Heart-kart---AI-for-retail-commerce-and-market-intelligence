#!/usr/bin/env python3
"""
Conversational AI Vendor Caller
Real-time AI agent that can listen, think, and respond naturally
"""

import asyncio
import json
import base64
import boto3
import os
from datetime import datetime
from typing import Dict, List, Optional

# AWS clients
transcribe_client = boto3.client('transcribe', region_name='us-east-1')
polly_client = boto3.client('polly', region_name='us-east-1')
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

class ConversationalAIAgent:
    """
    Real-time conversational AI agent for vendor calls
    """
    
    def __init__(self, call_context: Dict):
        self.call_context = call_context
        self.conversation_history = []
        self.vendor_name = call_context.get('vendor_name', 'Vendor')
        self.contact_person = call_context.get('contact_person', 'there')
        self.purpose = call_context.get('purpose', 'place_order')
        self.call_state = 'greeting'
        
        # Initialize conversation
        self.system_prompt = self._build_system_prompt()
        
    def _build_system_prompt(self) -> str:
        """Build the AI agent's personality and instructions"""
        return f"""You are Alex, a friendly and professional inventory manager at HeartKart, 
a Valentine's Day retail company. You're calling {self.vendor_name} to speak with {self.contact_person}.

Your personality:
- Warm, friendly, and professional
- Good listener - let them speak
- Patient and understanding
- Solution-oriented
- Natural conversationalist (use "um", "you know", etc. sparingly)

Your goal: {self.purpose}

Context:
{json.dumps(self.call_context, indent=2)}

Guidelines:
1. Start with a warm greeting and small talk
2. State your purpose clearly
3. Listen carefully to their responses
4. Handle objections gracefully
5. Confirm details before ending
6. Keep responses under 30 seconds
7. Sound human, not robotic
8. Use their name occasionally
9. Be ready to negotiate if needed
10. End warmly and professionally

Current conversation state: {self.call_state}

Respond naturally as if you're having a real phone conversation."""

    async def process_speech(self, audio_text: str) -> str:
        """
        Process vendor's speech and generate AI response
        
        Args:
            audio_text: Transcribed text from vendor
            
        Returns:
            AI-generated response text
        """
        # Add to conversation history
        self.conversation_history.append({
            'role': 'user',
            'content': audio_text,
            'timestamp': datetime.now().isoformat()
        })
        
        # Update call state based on conversation
        self._update_call_state(audio_text)
        
        # Generate AI response using Bedrock
        response_text = await self._generate_ai_response(audio_text)
        
        # Add AI response to history
        self.conversation_history.append({
            'role': 'assistant',
            'content': response_text,
            'timestamp': datetime.now().isoformat()
        })
        
        return response_text
    
    def _update_call_state(self, vendor_speech: str):
        """Update conversation state based on vendor's response"""
        speech_lower = vendor_speech.lower()
        
        if self.call_state == 'greeting':
            if any(word in speech_lower for word in ['good', 'fine', 'great', 'hello']):
                self.call_state = 'stating_purpose'
        
        elif self.call_state == 'stating_purpose':
            if any(word in speech_lower for word in ['yes', 'sure', 'okay', 'go ahead']):
                self.call_state = 'discussing_details'
            elif any(word in speech_lower for word in ['no', 'busy', 'not now']):
                self.call_state = 'handling_objection'
        
        elif self.call_state == 'discussing_details':
            if any(word in speech_lower for word in ['confirm', 'approved', 'sounds good']):
                self.call_state = 'confirming'
            elif any(word in speech_lower for word in ['question', 'what about', 'how about']):
                self.call_state = 'answering_questions'
        
        elif self.call_state == 'confirming':
            if any(word in speech_lower for word in ['yes', 'correct', 'right']):
                self.call_state = 'closing'
    
    async def _generate_ai_response(self, vendor_speech: str) -> str:
        """Generate AI response using Amazon Bedrock"""
        
        # Build conversation context
        conversation_context = "\n".join([
            f"{'Vendor' if msg['role'] == 'user' else 'You'}: {msg['content']}"
            for msg in self.conversation_history[-5:]  # Last 5 exchanges
        ])
        
        prompt = f"""{self.system_prompt}

Recent conversation:
{conversation_context}

Vendor just said: "{vendor_speech}"

Current state: {self.call_state}

Generate your natural response (keep it under 30 seconds when spoken):"""

        try:
            response = bedrock.invoke_model(
                modelId='us.amazon.nova-lite-v1:0',
                body=json.dumps({
                    'messages': [{'role': 'user', 'content': [{'text': prompt}]}],
                    'inferenceConfig': {'temperature': 0.7, 'maxTokens': 200}
                })
            )
            
            result = json.loads(response['body'].read())
            ai_response = result['output']['message']['content'][0]['text']
            
            # Clean up the response
            ai_response = ai_response.strip()
            
            # Remove any meta-commentary
            if ai_response.startswith(('You:', 'Alex:', 'Response:')):
                ai_response = ai_response.split(':', 1)[1].strip()
            
            return ai_response
            
        except Exception as e:
            print(f"Error generating AI response: {e}")
            return "I apologize, could you repeat that? I want to make sure I understand correctly."
    
    async def text_to_speech(self, text: str) -> bytes:
        """
        Convert text to speech using Amazon Polly
        
        Args:
            text: Text to convert
            
        Returns:
            Audio bytes in mulaw format for Twilio
        """
        try:
            response = polly_client.synthesize_speech(
                Text=text,
                OutputFormat='pcm',  # Raw PCM for real-time streaming
                VoiceId='Joanna',  # Natural female voice
                Engine='neural',  # Neural engine for more natural sound
                SampleRate='8000'  # 8kHz for telephony
            )
            
            audio_stream = response['AudioStream'].read()
            return audio_stream
            
        except Exception as e:
            print(f"Error in text-to-speech: {e}")
            return b''
    
    def get_opening_message(self) -> str:
        """Get the opening message for the call"""
        messages = {
            'place_order': f"Hi {self.contact_person}! This is Alex from HeartKart. How are you doing today?",
            'follow_up_late': f"Hi {self.contact_person}, this is Alex from HeartKart. Do you have a quick minute? I wanted to check on an order status.",
            'check_availability': f"Hi {self.contact_person}! Alex from HeartKart here. Hope you're having a good day! I wanted to check on some product availability with you.",
            'negotiate_pricing': f"Hi {self.contact_person}! It's Alex from HeartKart. Got a minute to chat about a potential bulk order?"
        }
        
        return messages.get(self.purpose, f"Hi {self.contact_person}! This is Alex from HeartKart calling.")
    
    def should_end_call(self) -> bool:
        """Determine if the call should end"""
        return self.call_state == 'closing' and len(self.conversation_history) > 6
    
    def get_call_summary(self) -> Dict:
        """Get summary of the call"""
        return {
            'vendor_name': self.vendor_name,
            'contact_person': self.contact_person,
            'purpose': self.purpose,
            'final_state': self.call_state,
            'conversation_length': len(self.conversation_history),
            'conversation_history': self.conversation_history,
            'timestamp': datetime.now().isoformat()
        }


# Example usage
if __name__ == '__main__':
    print("=" * 70)
    print("🤖 CONVERSATIONAL AI VENDOR CALLER")
    print("=" * 70)
    
    # Create AI agent
    call_context = {
        'vendor_name': 'Holiday Decor Wholesale',
        'contact_person': 'Sarah',
        'purpose': 'place_order',
        'order_details': {
            'items': ['Red Ornaments (100 units)', 'Gold Garland (50 units)'],
            'total_amount': 1250.00,
            'delivery_date': 'November 25th'
        }
    }
    
    agent = ConversationalAIAgent(call_context)
    
    print(f"\n📞 Simulating conversation with {call_context['vendor_name']}")
    print(f"Contact: {call_context['contact_person']}")
    print(f"Purpose: {call_context['purpose']}")
    print("\n" + "=" * 70)
    
    # Simulate conversation
    async def simulate_conversation():
        # Opening
        opening = agent.get_opening_message()
        print(f"\n🤖 AI Agent: {opening}")
        
        # Simulate vendor responses
        vendor_responses = [
            "Hi Alex! I'm doing well, thanks. How can I help you?",
            "Sure, what do you need?",
            "Let me check... yes, we have those in stock. When do you need them?",
            "November 25th should work. Let me confirm the pricing - $1,250 total?",
            "Perfect! I'll get that order processed today.",
            "You're welcome! Talk to you soon."
        ]
        
        for vendor_speech in vendor_responses:
            print(f"\n👤 Vendor: {vendor_speech}")
            
            # AI processes and responds
            ai_response = await agent.process_speech(vendor_speech)
            print(f"\n🤖 AI Agent: {ai_response}")
            
            # Check if should end
            if agent.should_end_call():
                print("\n📞 Call ending naturally...")
                break
            
            await asyncio.sleep(0.5)  # Simulate thinking time
        
        # Get summary
        summary = agent.get_call_summary()
        print("\n" + "=" * 70)
        print("📊 CALL SUMMARY")
        print("=" * 70)
        print(f"Final State: {summary['final_state']}")
        print(f"Exchanges: {summary['conversation_length']}")
        print(f"Duration: ~{summary['conversation_length'] * 15} seconds")
    
    # Run simulation
    asyncio.run(simulate_conversation())
