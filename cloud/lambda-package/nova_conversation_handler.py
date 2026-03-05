#!/usr/bin/env python3
"""
Nova-Powered Conversational AI for Vendor Calls
Uses Amazon Nova models for natural conversation
"""

import boto3
import json
import requests
import os
from typing import Dict, Any, List
from flask import Flask, request, Response

# AWS Clients
bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')

# In-memory conversation store
active_conversations = {}


def post_transcript_to_backend(call_sid: str, conversation: 'NovaConversation', decision: str):
    """Post transcript to backend for storage and display in frontend"""
    try:
        # Get API base URL
        api_url = os.getenv('API_BASE_URL', 'http://localhost:5000')
        if api_url.startswith('wss://'):
            api_url = api_url.replace('wss://', 'https://')
        elif api_url.startswith('ws://'):
            api_url = api_url.replace('ws://', 'http://')
        
        # Format transcript like Nova Sonic does
        transcript_data = []
        for msg in conversation.messages:
            role = 'assistant' if msg['role'] == 'assistant' else 'user'
            transcript_data.append({
                'role': role,
                'content': [{'text': msg['content']}]
            })
        
        # Post to backend
        response = requests.post(
            f'{api_url}/api/store-transcript',
            json={
                'call_sid': call_sid,
                'transcript': transcript_data,
                'decision': decision
            },
            timeout=5
        )
        
        if response.status_code == 200:
            print(f"✅ Transcript posted to backend for call {call_sid}")
            return True
        else:
            print(f"⚠️  Failed to post transcript: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"⚠️  Error posting transcript: {e}")
        return False

class NovaConversation:
    """Manages a conversation with Amazon Nova"""
    
    def __init__(self, call_sid: str, order_context: Dict[str, Any]):
        self.call_sid = call_sid
        self.order_context = order_context
        self.messages = []
        self.decision = None
        
        # Build initial system prompt
        self.system_prompt = self._build_system_prompt()
        
    def _build_system_prompt(self) -> str:
        """Create system prompt for Nova"""
        product = self.order_context.get('product_name', 'products')
        quantity = self.order_context.get('quantity', 0)
        vendor = self.order_context.get('vendor_name', 'the vendor')
        
        return f"""You are an AI assistant for HeartKart calling {vendor} to place an order.

ORDER DETAILS:
- Product: {product}
- Quantity: {quantity} units
- Vendor: {vendor}
- Delivery: As soon as possible (ideally within 1 week)
- Price: Market rate, negotiable

YOUR ROLE:
You are having a REAL phone conversation with a vendor. You must:

1. ANSWER THEIR QUESTIONS directly and specifically:
   - If they ask "when do you need it?" → Answer: "We need it as soon as possible, ideally within one week"
   - If they ask "what quantity?" → Answer: "{quantity} units of {product}"
   - If they ask "what's your budget?" → Answer: "We're flexible on price for quality products"
   - If they ask ANY question → ANSWER IT, don't just repeat your question

2. ASK FOLLOW-UP QUESTIONS if needed:
   - If they say "let me check" → Say: "Of course, please take your time"
   - If they mention partial availability → Ask: "How many units can you provide?"
   - If they mention delays → Ask: "When would they be available?"

3. MAKE A DECISION:
   - Once they clearly agree → Say: "Excellent! We'll send you the purchase order shortly"
   - Once they clearly decline → Say: "I understand, thank you for your time"
   - If very unclear after 3 turns → Say: "Let me follow up via email instead"

CRITICAL RULES:
- Keep responses under 40 words
- Sound natural and conversational
- ALWAYS answer vendor questions directly
- Don't just repeat "Can you fulfill this order?" if they ask you something
- Be helpful and professional

CONVERSATION GOAL: Determine if vendor can fulfill order (YES/NO/PARTIAL)"""

    def get_opening_message(self) -> str:
        """Generate opening message using Nova"""
        
        product = self.order_context.get('product_name', 'products')
        quantity = self.order_context.get('quantity', 0)
        
        # For the opening, use a template (faster and more reliable)
        opening = (
            f"Hello, this is the HeartKart AI ordering assistant. "
            f"I'm calling to place an order for {quantity} units of {product}. "
            f"Can you help me with this order?"
        )
        
        # Store in conversation history
        self.messages.append({
            'role': 'assistant',
            'content': opening
        })
        
        return opening
    
    def process_vendor_response(self, vendor_speech: str) -> Dict[str, Any]:
        """
        Process vendor's response using Nova
        Returns AI response and decision
        """
        
        # Add vendor message to history
        self.messages.append({
            'role': 'user',
            'content': f"[VENDOR]: {vendor_speech}"
        })
        
        # Build prompt for Nova with full context
        conversation_history = self._format_conversation()
        
        conversation_prompt = f"""
CONVERSATION SO FAR:
{conversation_history}

VENDOR JUST SAID: "{vendor_speech}"

INSTRUCTIONS:
1. If vendor asked a question → ANSWER IT DIRECTLY
2. If vendor agreed → Confirm and end positively
3. If vendor declined → Thank them and end politely
4. If unclear → Ask ONE clarifying question

Your response (under 40 words, conversational tone):"""
        
        print(f"\n🧠 Sending to Nova...")
        print(f"   Vendor said: \"{vendor_speech}\"")
        
        try:
            # Detect vendor questions and provide direct answers
            vendor_lower = vendor_speech.lower()
            
            # If vendor asks specific questions, answer them directly!
            if any(q in vendor_lower for q in ['when', 'what time', 'delivery', 'timeline']):
                ai_text = "We need them as soon as possible, ideally within one week. Can you fulfill this order?"
                print(f"   🎯 Detected 'when' question - answering directly")
            elif any(q in vendor_lower for q in ['what do you need', 'what quantity', 'how many', 'how much']):
                ai_text = f"We need {self.order_context.get('quantity', 50)} units of {self.order_context.get('product_name', 'Valentine gifts')}. Can you provide them?"
                print(f"   🎯 Detected 'what' question - answering directly")
            elif any(q in vendor_lower for q in ['budget', 'price', 'cost', 'how much']):
                ai_text = "We're flexible on pricing for quality products. Can you fulfill this order?"
                print(f"   🎯 Detected pricing question - answering directly")
            else:
                # Use Nova for other responses
                response = bedrock_runtime.invoke_model(
                    modelId='us.amazon.nova-micro-v1:0',  # Fast, cost-effective
                    body=json.dumps({
                        "messages": [
                            {
                                "role": "user",
                                "content": f"{self.system_prompt}\n\n{conversation_prompt}"
                            }
                        ],
                        "inferenceConfig": {
                            "temperature": 0.8,
                            "maxTokens": 150,
                            "topP": 0.95
                        }
                    }),
                    contentType='application/json',
                    accept='application/json'
                )
                
                response_body = json.loads(response['body'].read())
                ai_text = response_body['output']['message']['content'][0]['text'].strip()
                
                # Clean up the response
                ai_text = ai_text.replace('[AI]:', '').replace('[ASSISTANT]:', '').strip()
                ai_text = ai_text.replace('\n', ' ').strip()
                
                response_body = json.loads(response['body'].read())
                ai_text = response_body['output']['message']['content'][0]['text'].strip()
                
                # Clean up the response
                ai_text = ai_text.replace('[AI]:', '').replace('[ASSISTANT]:', '').strip()
                ai_text = ai_text.replace('\n', ' ').strip()
            
            print(f"   🤖 Nova/AI says: \"{ai_text}\"")
            
        except Exception as e:
            print(f"   ❌ Nova error: {e}")
            # Fallback to simple response
            ai_text = self._fallback_response(vendor_speech)
        
        # Add AI response to history
        self.messages.append({
            'role': 'assistant',
            'content': ai_text
        })
        
        # Analyze for decision
        decision = self._extract_decision(vendor_speech, ai_text)
        
        if decision:
            self.decision = decision
            print(f"   ✅ Decision: {decision}")
        
        return {
            'text': ai_text,
            'decision': decision,
            'should_end': decision is not None
        }
    
    def _format_conversation(self) -> str:
        """Format conversation history for Nova"""
        formatted = []
        for msg in self.messages:
            role = "AI" if msg['role'] == 'assistant' else "VENDOR"
            formatted.append(f"[{role}]: {msg['content']}")
        return '\n'.join(formatted)
    
    def _extract_decision(self, vendor_speech: str, ai_response: str) -> str:
        """Extract YES/NO decision from conversation"""
        
        vendor_lower = vendor_speech.lower()
        ai_lower = ai_response.lower()
        
        # Strong YES indicators
        yes_keywords = ['yes', 'sure', 'absolutely', 'can do', 'we can', 'no problem',
                       'of course', 'definitely', 'sounds good', 'perfect', 'great']
        
        # Strong NO indicators
        no_keywords = ['no', 'cannot', "can't", 'unable', 'impossible', 'sorry',
                      "won't", 'unavailable', "don't have", 'out of stock']
        
        # Ending indicators (AI finishing conversation)
        ending_phrases = ['purchase order', 'send you', 'follow up', 'thank you for your time',
                         'we\'ll be in touch', 'goodbye']
        
        # Count indicators in vendor speech
        yes_count = sum(1 for k in yes_keywords if k in vendor_lower)
        no_count = sum(1 for k in no_keywords if k in vendor_lower)
        
        # Check if AI is ending the conversation
        ai_ending = any(phrase in ai_lower for phrase in ending_phrases)
        
        if ai_ending:
            if yes_count > 0:
                return 'YES'
            elif no_count > 0:
                return 'NO'
        
        # Strong signals
        if yes_count > no_count and yes_count >= 2:
            return 'YES'
        elif no_count > yes_count and no_count >= 2:
            return 'NO'
        
        return None  # UNCLEAR
    
    def _fallback_response(self, vendor_speech: str) -> str:
        """Fallback response if Nova fails"""
        vendor_lower = vendor_speech.lower()
        
        if any(word in vendor_lower for word in ['yes', 'sure', 'can do', 'absolutely']):
            return "Excellent! We'll send you the purchase order shortly. Thank you!"
        elif any(word in vendor_lower for word in ['no', 'cannot', "can't", 'sorry']):
            return "I understand. Thank you for your time."
        else:
            return "Could you please confirm - can you fulfill this order? Yes or no?"
    
    def get_result(self) -> Dict[str, Any]:
        """Get final conversation result"""
        return {
            'decision': self.decision,
            'messages': self.messages,
            'transcript': self._format_conversation()
        }


# Flask integration functions
def generate_opening_twiml(call_sid: str, context: Dict[str, Any]) -> str:
    """Generate TwiML for the opening message"""
    
    # Create Nova conversation
    conversation = NovaConversation(call_sid, context)
    opening_message = conversation.get_opening_message()
    
    # Store conversation
    active_conversations[call_sid] = conversation
    
    # Use absolute URL for Twilio webhook
    import os
    api_url = os.getenv('API_URL', 'https://h1p3mb0sh9.execute-api.us-east-1.amazonaws.com')
    
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" 
            timeout="5" 
            speechTimeout="auto" 
            action="{api_url}/ai-voice/process-response?call_sid={call_sid}" 
            method="POST">
        <Say voice="Polly.Joanna">{opening_message}</Say>
    </Gather>
    <Say voice="Polly.Joanna">I didn't hear a response. Goodbye.</Say>
</Response>"""


def generate_response_twiml(call_sid: str, vendor_speech: str) -> str:
    """Process vendor response and generate AI reply using Nova"""
    
    # Get conversation
    conversation = active_conversations.get(call_sid)
    
    if not conversation:
        # Shouldn't happen, but handle gracefully
        return """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">Thank you for your time.</Say>
    <Hangup/>
</Response>"""
    
    # Process response with Nova
    result = conversation.process_vendor_response(vendor_speech)
    
    ai_response = result['text']
    decision = result['decision']
    should_end = result['should_end']
    
    # If we have a decision, end the call
    if should_end:
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">{ai_response}</Say>
    <Pause length="1"/>
    <Hangup/>
</Response>"""
    
    # Otherwise, continue conversation
    import os
    api_url = os.getenv('API_URL', 'https://h1p3mb0sh9.execute-api.us-east-1.amazonaws.com')
    
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" 
            timeout="5" 
            speechTimeout="auto" 
            action="{api_url}/ai-voice/process-response?call_sid={call_sid}" 
            method="POST">
        <Say voice="Polly.Joanna">{ai_response}</Say>
    </Gather>
    <Say voice="Polly.Joanna">Thank you for your time. Goodbye.</Say>
</Response>"""


def get_conversation_result(call_sid: str) -> Dict[str, Any]:
    """Get final result of conversation"""
    conversation = active_conversations.get(call_sid)
    
    if not conversation:
        return {
            'decision': 'UNKNOWN',
            'transcript': 'No conversation found',
            'history': []
        }
    
    result = conversation.get_result()
    
    return {
        'decision': result.get('decision', 'UNKNOWN'),
        'history': result.get('messages', []),
        'transcript': result.get('transcript', '')
    }

