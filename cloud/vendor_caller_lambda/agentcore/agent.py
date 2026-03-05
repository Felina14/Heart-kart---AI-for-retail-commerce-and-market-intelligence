"""
Vendor Caller Agent for AWS Bedrock AgentCore Runtime
Generates AI-powered call scripts and manages vendor communication
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# Initialize AgentCore App
app = BedrockAgentCoreApp()

# Initialize AWS clients
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# Initialize OpenSearch
credentials = boto3.Session().get_credentials()
awsauth = AWS4Auth(
    credentials.access_key,
    credentials.secret_key,
    'us-east-1',
    'es',
    session_token=credentials.token
)

opensearch_client = OpenSearch(
    hosts=[{'host': 'search-christmas-catalog-bcl77whynen7enbam5vr4rjgeu.us-east-1.es.amazonaws.com', 'port': 443}],
    http_auth=awsauth,
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection
)


def get_vendor_info(vendor_name: str) -> Optional[Dict]:
    """Get vendor contact information from OpenSearch"""
    try:
        response = opensearch_client.search(
            index='valentines-catalog',
            body={
                'query': {'term': {'vendor_name.keyword': vendor_name}},
                'size': 1,
                '_source': ['vendor_name', 'vendor_phone', 'vendor_email', 'vendor_contact_person']
            }
        )
        
        if response['hits']['hits']:
            vendor = response['hits']['hits'][0]['_source']
            return {
                'name': vendor.get('vendor_name', vendor_name),
                'phone': vendor.get('vendor_phone', ''),
                'email': vendor.get('vendor_email', ''),
                'contact_person': vendor.get('vendor_contact_person', '')
            }
    except Exception as e:
        print(f"Error fetching vendor: {e}")
    
    # Return mock data if not found
    return {
        'name': vendor_name,
        'phone': '+1-555-VENDOR',
        'email': f'contact@{vendor_name.lower().replace(" ", "")}.com',
        'contact_person': 'Vendor Representative'
    }


def generate_call_script(call_type: str, context: Dict) -> str:
    """Generate AI-powered call script using Bedrock"""
    
    prompts = {
        'place_order': f"""Generate a professional phone call script for placing a purchase order.

Context:
- Vendor: {context.get('vendor_name')}
- Contact: {context.get('contact_person', 'the vendor representative')}
- Order Details: {context.get('order_details')}
- Total Amount: ${context.get('total_amount', 0):.2f}
- Delivery Date: {context.get('delivery_date')}

Create a concise, professional script (under 60 seconds) that:
1. Introduces yourself as HeartKart Inventory Manager
2. States the purpose (placing a purchase order)
3. Provides order details clearly
4. Confirms delivery timeline
5. Asks for order confirmation
6. Thanks them

Keep it conversational and professional.""",

        'follow_up_late': f"""Generate a professional phone call script for following up on a late delivery.

Context:
- Vendor: {context.get('vendor_name')}
- PO Number: {context.get('po_number')}
- Expected Delivery: {context.get('expected_date')}
- Days Late: {context.get('days_late')}

Create a polite but firm script (under 45 seconds) that:
1. Introduces yourself
2. References the PO number
3. Notes the delivery is late
4. Asks for updated ETA
5. Maintains professional relationship

Keep it diplomatic but clear.""",

        'check_availability': f"""Generate a professional phone call script for checking stock availability.

Context:
- Vendor: {context.get('vendor_name')}
- Items Needed: {context.get('items')}
- Quantity: {context.get('quantity')}
- Urgency: {context.get('urgency', 'standard')}

Create a brief script (under 30 seconds) that:
1. Introduces yourself
2. Asks about stock availability
3. Requests lead time
4. Thanks them

Keep it quick and direct."""
    }
    
    prompt = prompts.get(call_type, prompts['place_order'])
    
    try:
        response = bedrock.invoke_model(
            modelId='us.amazon.nova-lite-v1:0',
            body=json.dumps({
                'messages': [{'role': 'user', 'content': [{'text': prompt}]}],
                'inferenceConfig': {'temperature': 0.3, 'maxTokens': 800}
            })
        )
        
        result = json.loads(response['body'].read())
        return result['output']['message']['content'][0]['text']
        
    except Exception as e:
        print(f"Error generating script: {e}")
        return f"Error generating call script: {str(e)}"


def log_call_attempt(call_data: Dict) -> bool:
    """Log call attempt to DynamoDB"""
    try:
        table = dynamodb.Table('vendor-call-logs')
        table.put_item(Item=call_data)
        return True
    except Exception as e:
        print(f"Error logging call: {e}")
        return False


@app.entrypoint
def vendor_caller_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    AgentCore Runtime entry point for Vendor Caller Agent
    
    Args:
        payload: {
            'vendor_name': str,
            'call_type': str (place_order, follow_up_late, check_availability),
            'context': dict (call-specific context),
            'phone_number': str (optional override)
        }
        
    Returns:
        Dictionary with call script and vendor info
    """
    print(f"Received request: {json.dumps(payload, default=str)}")
    
    try:
        vendor_name = payload.get('vendor_name')
        call_type = payload.get('call_type', 'place_order')
        context = payload.get('context', {})
        phone_override = payload.get('phone_number')
        
        if not vendor_name:
            return {
                'status': 'error',
                'error': 'vendor_name is required'
            }
        
        # Get vendor information
        vendor_info = get_vendor_info(vendor_name)
        
        # Use override phone if provided
        phone = phone_override or vendor_info.get('phone', '')
        
        # Add vendor info to context
        context['vendor_name'] = vendor_info['name']
        context['contact_person'] = vendor_info.get('contact_person', 'the vendor representative')
        
        # Generate call script
        script = generate_call_script(call_type, context)
        
        # Create call log
        call_id = f"CALL-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        call_data = {
            'call_id': call_id,
            'vendor_name': vendor_name,
            'phone_number': phone,
            'call_type': call_type,
            'script': script,
            'context': json.dumps(context),
            'status': 'script_generated',
            'timestamp': datetime.now().isoformat()
        }
        
        # Log to DynamoDB
        log_call_attempt(call_data)
        
        return {
            'status': 'success',
            'call_id': call_id,
            'vendor_name': vendor_name,
            'vendor_info': vendor_info,
            'phone_number': phone,
            'call_type': call_type,
            'script': script,
            'timestamp': datetime.now().isoformat(),
            'message': 'Call script generated successfully. Use Lambda function to initiate actual call.'
        }
        
    except Exception as e:
        import traceback
        print(f"Error in handler: {e}")
        traceback.print_exc()
        return {
            'status': 'error',
            'message': str(e),
            'traceback': traceback.format_exc()
        }


if __name__ == "__main__":
    # Run the AgentCore Runtime server
    app.run()
