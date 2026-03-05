#!/usr/bin/env python3
"""
Vendor Auto-Caller Agent
Automates vendor communication via Twilio + Bedrock
Uses Amazon Nova for script generation
"""

import json
import boto3
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather

# Initialize clients
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# Import product data access layer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from product_data_access import get_products_by_vendor

# Twilio configuration
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN', '')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER', '')
WEBHOOK_BASE_URL = os.getenv('WEBHOOK_BASE_URL', 'http://localhost:5000')

# Initialize Twilio client
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    try:
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    except Exception as e:
        print(f"Warning: Could not initialize Twilio client: {e}")

# DynamoDB table for call logs
try:
    call_logs_table = dynamodb.Table('vendor-call-logs')
except:
    call_logs_table = None


def get_vendor_info(vendor_name: str) -> Dict:
    """Get vendor contact information from DynamoDB or mock data."""
    mock_vendors = {
        'Holiday Decor Wholesale': {
            'name': 'Holiday Decor Wholesale',
            'phone': '+1-555-0123',
            'email': 'orders@holidaydecor.com',
            'contact_person': 'Sarah Johnson'
        },
        'Evergreen Suppliers': {
            'name': 'Evergreen Suppliers',
            'phone': '+1-555-0456',
            'email': 'sales@evergreensuppliers.com',
            'contact_person': 'Mike Chen'
        },
        'Winter Wonderland Imports': {
            'name': 'Winter Wonderland Imports',
            'phone': '+1-555-0789',
            'email': 'contact@winterwonderland.com',
            'contact_person': 'Emily Rodriguez'
        }
    }
    
    try:
        products = get_products_by_vendor(vendor_name, limit=1)
        if products:
            product = products[0]
            return {
                'name': product.get('vendor_name', vendor_name),
                'phone': product.get('vendor_phone', ''),
                'email': product.get('vendor_email', ''),
                'contact_person': product.get('vendor_contact_person', '')
            }
    except Exception as e:
        print(f"DynamoDB lookup failed, using mock data: {e}")
    
    if vendor_name in mock_vendors:
        return mock_vendors[vendor_name]
    
    return {
        'name': vendor_name,
        'phone': '+1-555-VENDOR',
        'email': f'contact@{vendor_name.lower().replace(" ", "")}.com',
        'contact_person': 'Vendor Representative'
    }


def generate_call_script(call_type: str, context: Dict) -> str:
    """Generate AI-powered call script using Amazon Nova."""
    prompts = {
        'place_order': f"""Generate a professional phone call script for placing a purchase order with a vendor.

Context:
- Vendor: {context.get('vendor_name')}
- Contact Person: {context.get('contact_person', 'the vendor representative')}
- Order Details: {context.get('order_details')}
- Total Amount: ${context.get('total_amount', 0):.2f}
- Delivery Date Needed: {context.get('delivery_date')}

Create a concise, professional script that:
1. Introduces yourself as HeartKart Inventory Manager
2. States the purpose (placing a purchase order)
3. Provides order details clearly
4. Confirms delivery timeline
5. Asks for order confirmation
6. Thanks them and provides callback number

Keep it under 60 seconds when spoken.""",

        'follow_up_late': f"""Generate a professional phone call script for following up on a late delivery.

Context:
- Vendor: {context.get('vendor_name')}
- PO Number: {context.get('po_number')}
- Expected Delivery: {context.get('expected_date')}
- Days Late: {context.get('days_late')}
- Items: {context.get('items')}

Create a polite but firm script that:
1. Introduces yourself
2. References the PO number
3. Notes the delivery is late
4. Asks for updated ETA
5. Requests confirmation
6. Maintains professional relationship

Keep it under 45 seconds.""",

        'check_availability': f"""Generate a professional phone call script for checking stock availability.

Context:
- Vendor: {context.get('vendor_name')}
- Items Needed: {context.get('items')}
- Quantity: {context.get('quantity')}
- Urgency: {context.get('urgency', 'standard')}

Create a brief script that:
1. Introduces yourself
2. Asks about stock availability
3. Requests lead time
4. Asks about pricing for quantity
5. Thanks them

Keep it under 30 seconds.""",

        'negotiate_pricing': f"""Generate a professional phone call script for negotiating bulk pricing.

Context:
- Vendor: {context.get('vendor_name')}
- Items: {context.get('items')}
- Current Price: ${context.get('current_price', 0):.2f}
- Quantity: {context.get('quantity')}
- Target Price: ${context.get('target_price', 0):.2f}

Create a diplomatic script that:
1. Introduces yourself
2. Mentions long-term relationship
3. Proposes bulk order
4. Asks about volume discount
5. Suggests target price range
6. Remains flexible

Keep it under 45 seconds."""
    }
    
    prompt = prompts.get(call_type, prompts['place_order'])
    
    try:
        response = bedrock.invoke_model(
            modelId='us.amazon.nova-lite-v1:0',
            body=json.dumps({
                'messages': [{'role': 'user', 'content': [{'text': prompt}]}],
                'inferenceConfig': {'temperature': 0.3, 'maxTokens': 1000}
            })
        )
        
        result = json.loads(response['body'].read())
        return result['output']['message']['content'][0]['text']
        
    except Exception as e:
        print(f"Error generating script: {e}")
        return "Error generating call script"


def initiate_call(
    vendor_name: str,
    call_type: str,
    context: Dict,
    phone_number: Optional[str] = None
) -> Dict:
    """Initiate an automated call to vendor."""
    print(f"📞 Initiating {call_type} call to {vendor_name}...")
    
    vendor_info = get_vendor_info(vendor_name)
    if not vendor_info:
        return {
            'status': 'error',
            'error': f'Vendor {vendor_name} not found',
            'timestamp': datetime.now().isoformat()
        }
    
    phone = phone_number or vendor_info.get('phone', '')
    if not phone:
        return {
            'status': 'error',
            'error': f'No phone number available for {vendor_name}',
            'vendor_info': vendor_info,
            'timestamp': datetime.now().isoformat()
        }
    
    context['vendor_name'] = vendor_info['name']
    context['contact_person'] = vendor_info.get('contact_person', 'the vendor representative')
    
    script = generate_call_script(call_type, context)
    
    call_log = {
        'call_id': f"CALL-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        'vendor_name': vendor_name,
        'phone_number': phone,
        'call_type': call_type,
        'script': script,
        'context': context,
        'status': 'initiated',
        'timestamp': datetime.now().isoformat()
    }
    
    twilio_call_sid = None
    call_status = 'script_generated'
    
    if twilio_client and TWILIO_PHONE_NUMBER:
        try:
            twiml_url = f"{WEBHOOK_BASE_URL}/api/vendor/twiml/{call_log['call_id']}"
            recording_callback = f"{WEBHOOK_BASE_URL}/api/vendor/recording/{call_log['call_id']}"
            status_callback = f"{WEBHOOK_BASE_URL}/api/vendor/status/{call_log['call_id']}"
            
            call = twilio_client.calls.create(
                to=phone,
                from_=TWILIO_PHONE_NUMBER,
                url=twiml_url,
                method='POST',
                record=True,
                recording_status_callback=recording_callback,
                status_callback=status_callback
            )
            
            twilio_call_sid = call.sid
            call_status = 'calling'
            call_log['twilio_call_sid'] = twilio_call_sid
            call_log['status'] = call_status
            
            print(f"✅ Call initiated! Twilio SID: {twilio_call_sid}")
            
        except Exception as e:
            print(f"⚠️ Twilio call failed: {e}")
            call_status = 'twilio_error'
            call_log['error'] = str(e)
    else:
        print("ℹ️ Twilio not configured.")
    
    try:
        if call_logs_table:
            import decimal
            call_log_copy = json.loads(json.dumps(call_log), parse_float=decimal.Decimal)
            call_logs_table.put_item(Item=call_log_copy)
    except Exception as e:
        print(f"Warning: Could not save call log: {e}")
    
    response = {
        'status': 'success',
        'call_id': call_log['call_id'],
        'vendor_name': vendor_name,
        'phone_number': phone,
        'call_type': call_type,
        'script': script,
        'call_status': call_status,
        'timestamp': datetime.now().isoformat()
    }
    
    if twilio_call_sid:
        response['twilio_call_sid'] = twilio_call_sid
        response['message'] = f'✅ Call initiated to {vendor_name}! Twilio is dialing {phone}...'
    else:
        response['message'] = 'Call script generated. Configure Twilio to make actual calls.'
    
    return response


def call_vendor_for_po(po_data: Dict) -> Dict:
    """Convenience function to call vendor when PO is generated."""
    context = {
        'order_details': f"{len(po_data.get('items', []))} items",
        'total_amount': po_data.get('total_cost', 0),
        'delivery_date': po_data.get('expected_delivery', 'as soon as possible'),
        'po_number': po_data.get('po_number', 'TBD'),
        'items': ', '.join([f"{item['name']} (qty: {item['quantity']})" 
                           for item in po_data.get('items', [])[:3]])
    }
    
    return initiate_call(
        vendor_name=po_data.get('vendor', 'Unknown'),
        call_type='place_order',
        context=context
    )


def follow_up_late_delivery(po_number: str, vendor_name: str, days_late: int, items: List[str]) -> Dict:
    """Follow up on late delivery."""
    context = {
        'po_number': po_number,
        'expected_date': f"{days_late} days ago",
        'days_late': days_late,
        'items': ', '.join(items[:3])
    }
    
    return initiate_call(
        vendor_name=vendor_name,
        call_type='follow_up_late',
        context=context
    )


def check_stock_availability(vendor_name: str, items: List[str], quantity: int, urgency: str = 'standard') -> Dict:
    """Check stock availability with vendor."""
    context = {
        'items': ', '.join(items),
        'quantity': quantity,
        'urgency': urgency
    }
    
    return initiate_call(
        vendor_name=vendor_name,
        call_type='check_availability',
        context=context
    )


def negotiate_bulk_pricing(vendor_name: str, items: List[str], quantity: int, current_price: float, target_price: float) -> Dict:
    """Negotiate pricing for bulk orders."""
    context = {
        'items': ', '.join(items),
        'quantity': quantity,
        'current_price': current_price,
        'target_price': target_price
    }
    
    return initiate_call(
        vendor_name=vendor_name,
        call_type='negotiate_pricing',
        context=context
    )


def generate_twiml_for_call(call_id: str, script: str) -> str:
    """Generate TwiML for the call."""
    response = VoiceResponse()
    
    response.say(
        script,
        voice='Polly.Joanna',
        language='en-US'
    )
    
    gather = Gather(
        input='speech',
        action=f'/api/vendor/response/{call_id}',
        method='POST',
        speech_timeout='auto'
    )
    gather.say(
        "Please respond after the beep.",
        voice='Polly.Joanna'
    )
    response.append(gather)
    
    response.say(
        "Thank you. We'll follow up via email. Goodbye!",
        voice='Polly.Joanna'
    )
    
    return str(response)


def get_call_history(vendor_name: Optional[str] = None, limit: int = 10) -> List[Dict]:
    """Get call history from DynamoDB."""
    if not call_logs_table:
        return []
    
    try:
        if vendor_name:
            response = call_logs_table.query(
                IndexName='vendor-index',
                KeyConditionExpression='vendor_name = :vendor',
                ExpressionAttributeValues={':vendor': vendor_name},
                Limit=limit,
                ScanIndexForward=False
            )
        else:
            response = call_logs_table.scan(Limit=limit)
        
        return response.get('Items', [])
        
    except Exception as e:
        print(f"Error fetching call history: {e}")
        return []


if __name__ == '__main__':
    print("=" * 70)
    print("📞 VENDOR AUTO-CALLER - Powered by Amazon Nova")
    print("=" * 70)
    
    print("\n🔹 Example 1: Placing a Purchase Order")
    po_data = {
        'vendor': 'Holiday Decor Wholesale',
        'po_number': 'PO-2026-001',
        'items': [
            {'name': 'Red Ornaments', 'quantity': 100},
            {'name': 'Gold Garland', 'quantity': 50},
            {'name': 'Valentine Lights', 'quantity': 75}
        ],
        'total_cost': 1250.00,
        'expected_delivery': '2026-02-10'
    }
    
    result = call_vendor_for_po(po_data)
    print(f"\nStatus: {result['status']}")
    print(f"Call ID: {result.get('call_id')}")
    print(f"\n📝 Generated Script:\n{result.get('script', 'N/A')}")
    
    print("\n" + "=" * 70)
