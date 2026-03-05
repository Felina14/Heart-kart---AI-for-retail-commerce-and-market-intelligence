"""
Nova Sonic Agent V2 - Improved YES/NO detection
Uses the working Nova Sonic implementation with better prompts
"""

import asyncio
import os
from typing import Dict, Any
from agent_prompts import (
    get_vendor_call_system_prompt,
    get_vendor_greeting_prompt,
    get_order_presentation_prompt,
    get_yes_confirmation_prompt,
    get_no_acknowledgment_prompt
)


async def make_nova_sonic_call(vendor_name: str, vendor_phone: str,
                               product_info: Dict[str, Any],
                               order_details: Dict[str, Any]) -> Dict[str, Any]:
    """
    Make a call using Nova Sonic with improved prompts
    
    This is a wrapper around the existing Nova Sonic implementation
    that adds better prompting for YES/NO detection
    
    Args:
        vendor_name: Name of vendor to call
        vendor_phone: Phone number
        product_info: Product details
        order_details: Order details
        
    Returns:
        {
            'call_sid': str,
            'transcript': str,
            'duration': int,
            'status': str
        }
    """
    print(f"📞 Initiating Nova Sonic call to {vendor_name} at {vendor_phone}")
    
    # Build context for Nova Sonic
    call_context = {
        'vendor_name': vendor_name,
        'vendor_phone': vendor_phone,
        'product_name': product_info.get('name', 'products'),
        'quantity': order_details.get('quantity', 0),
        'delivery_date': order_details.get('delivery_date', 'as soon as possible'),
        'total_amount': order_details.get('total_amount', 0),
        'items': order_details.get('items', []),
        'system_prompt': get_vendor_call_system_prompt(vendor_name, order_details),
        'greeting': get_vendor_greeting_prompt(vendor_name),
        'order_presentation': get_order_presentation_prompt(order_details)
    }
    
    try:
        # Use the existing Nova Sonic implementation
        # This calls the /api/call-vendor endpoint which handles the actual call
        import requests
        
        api_url = os.getenv('API_URL', 'http://localhost:5000')
        
        response = requests.post(
            f'{api_url}/api/call-vendor',
            json={
                'vendor_phone': vendor_phone,
                'vendor_name': vendor_name,
                'contact_person': 'there',
                'product_name': product_info.get('name'),
                'quantity': order_details.get('quantity'),
                'po_number': f"DRAFT-{vendor_name[:3].upper()}",
                'items': order_details.get('items', []),
                'delivery_date': order_details.get('delivery_date'),
                'total_amount': order_details.get('total_amount'),
                'context': call_context
            },
            timeout=120
        )
        
        if response.status_code == 200:
            result = response.json()
            call_sid = result.get('call_sid')
            
            print(f"   ✅ Call initiated: {call_sid}")
            
            # Wait for call to complete and get transcript
            transcript = await wait_for_call_completion(call_sid, api_url)
            
            return {
                'call_sid': call_sid,
                'transcript': transcript,
                'duration': len(transcript.split()) * 2,  # Rough estimate
                'status': 'completed'
            }
        else:
            print(f"   ❌ Call failed: {response.status_code}")
            return {
                'call_sid': None,
                'transcript': '',
                'duration': 0,
                'status': 'failed',
                'error': f"HTTP {response.status_code}"
            }
            
    except Exception as e:
        print(f"   ❌ Error making call: {e}")
        return {
            'call_sid': None,
            'transcript': '',
            'duration': 0,
            'status': 'failed',
            'error': str(e)
        }


async def wait_for_call_completion(call_sid: str, api_url: str, max_wait: int = 120) -> str:
    """
    Wait for call to complete and retrieve transcript
    
    Args:
        call_sid: Twilio call SID
        api_url: API base URL
        max_wait: Maximum seconds to wait
        
    Returns:
        Call transcript
    """
    import requests
    import time
    
    print(f"   ⏳ Waiting for call to complete...")
    
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        try:
            # Check call status
            response = requests.get(
                f'{api_url}/api/get-call-status/{call_sid}',
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                status = data.get('status', '')
                
                if status in ['completed', 'failed', 'busy', 'no-answer']:
                    print(f"   ✅ Call {status}")
                    
                    # Try to get transcript
                    # For now, return a placeholder since transcript retrieval
                    # depends on Twilio transcription which takes time
                    # In production, this would poll for the transcript
                    
                    # Simulate transcript for testing
                    transcript = await get_call_transcript(call_sid, api_url)
                    
                    return transcript
            
            # Wait before checking again
            await asyncio.sleep(5)
            
        except Exception as e:
            print(f"   ⚠️  Error checking call status: {e}")
            await asyncio.sleep(5)
    
    print(f"   ⏰ Timeout waiting for call completion")
    return ""


async def get_call_transcript(call_sid: str, api_url: str) -> str:
    """
    Get transcript from completed call
    
    In production, this would retrieve the actual transcript from Twilio
    For now, returns a simulated transcript based on call outcome
    """
    # TODO: Implement actual transcript retrieval from Twilio
    # This requires:
    # 1. Waiting for Twilio to generate transcription
    # 2. Fetching transcription via Twilio API
    # 3. Parsing and formatting the transcript
    
    # For now, return placeholder
    # The orchestrator will handle this via the WebSocket server
    # which captures the real-time conversation
    
    return f"[Transcript for call {call_sid} - Retrieved from WebSocket server]"


# For testing without actual calls
async def simulate_vendor_call(vendor_name: str, vendor_phone: str,
                               product_info: Dict[str, Any],
                               order_details: Dict[str, Any],
                               simulated_response: str = 'YES') -> Dict[str, Any]:
    """
    Simulate a vendor call for testing
    
    Args:
        simulated_response: 'YES', 'NO', or 'MAYBE'
    """
    print(f"🎭 SIMULATING call to {vendor_name}")
    
    await asyncio.sleep(2)  # Simulate call duration
    
    # Generate simulated transcript
    if simulated_response == 'YES':
        transcript = f"""
Agent: Hello, this is Sarah from HeartKart. I'm calling to speak with someone from {vendor_name}.
{vendor_name}: Yes, this is {vendor_name}. How can I help?
Agent: We'd like to place an order for {order_details.get('quantity')} units of {product_info.get('name')}.
Agent: We need delivery by {order_details.get('delivery_date')}. Can you fulfill this order?
{vendor_name}: Yes, we can definitely do that. No problem at all.
Agent: Excellent! The total is ${order_details.get('total_amount', 0):.2f}. Is that acceptable?
{vendor_name}: Yes, that works for us.
Agent: Great! We'll send you a formal purchase order via email. Thank you!
{vendor_name}: Thank you!
"""
    elif simulated_response == 'NO':
        transcript = f"""
Agent: Hello, this is Sarah from HeartKart. I'm calling to speak with someone from {vendor_name}.
{vendor_name}: Yes, this is {vendor_name}. How can I help?
Agent: We'd like to place an order for {order_details.get('quantity')} units of {product_info.get('name')}.
Agent: We need delivery by {order_details.get('delivery_date')}. Can you fulfill this order?
{vendor_name}: I'm sorry, but we're completely out of stock on those items right now.
Agent: I understand. Thank you for your time.
{vendor_name}: Sorry we couldn't help. Good luck!
"""
    else:  # MAYBE
        transcript = f"""
Agent: Hello, this is Sarah from HeartKart. I'm calling to speak with someone from {vendor_name}.
{vendor_name}: Yes, this is {vendor_name}. How can I help?
Agent: We'd like to place an order for {order_details.get('quantity')} units of {product_info.get('name')}.
Agent: We need delivery by {order_details.get('delivery_date')}. Can you fulfill this order?
{vendor_name}: Let me check with our warehouse and get back to you on that.
Agent: Okay, thank you.
"""
    
    return {
        'call_sid': f'CA-SIMULATED-{vendor_name[:5].upper()}',
        'transcript': transcript.strip(),
        'duration': 45,
        'status': 'completed',
        'simulated': True
    }


if __name__ == '__main__':
    # Test the agent
    test_vendor = 'Holiday Supplies Inc'
    test_phone = '+15555551234'
    
    test_product = {
        'name': 'Valentine Ornaments',
        'category': 'Ornaments'
    }
    
    test_order = {
        'quantity': 500,
        'delivery_date': '2025-12-15',
        'total_amount': 2500.00,
        'items': [
            {'name': 'Red Ornaments', 'quantity': 300},
            {'name': 'Gold Ornaments', 'quantity': 200}
        ]
    }
    
    print("Testing Nova Sonic Agent V2")
    print()
    
    # Test with simulated calls
    for response_type in ['YES', 'NO', 'MAYBE']:
        print(f"\nTest: Simulated {response_type} response")
        result = asyncio.run(simulate_vendor_call(
            test_vendor, test_phone, test_product, test_order, response_type
        ))
        print(f"Call SID: {result['call_sid']}")
        print(f"Duration: {result['duration']}s")
        print(f"Transcript preview: {result['transcript'][:100]}...")
        print()
