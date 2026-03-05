"""
Lambda function to handle Twilio webhooks
Initiates calls and handles TwiML responses
"""

import json
import os
import base64
import re
import boto3
from datetime import datetime
from urllib.parse import parse_qs
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

# Environment variables
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')
AGENTCORE_AGENT_ARN = os.environ.get('AGENTCORE_AGENT_ARN')

# Initialize clients
bedrock_agentcore = boto3.client('bedrock-agentcore', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID else None


def lambda_handler(event, context):
    """
    Main Lambda handler for Twilio webhooks
    
    Routes:
    - POST /initiate-call - Start a new call
    - POST /voice - TwiML for call
    - POST /status - Call status updates
    """
    
    print(f"Event: {json.dumps(event)}")
    
    # Parse request - handle both API Gateway v1 and v2 formats
    http_method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method', 'POST')
    path = event.get('path') or event.get('rawPath', '')
    body_raw = event.get('body', '')
    
    # Decode base64 if needed (API Gateway v2)
    if event.get('isBase64Encoded', False):
        import base64
        body_raw = base64.b64decode(body_raw).decode('utf-8')
    
    # Parse body based on content type
    content_type = event.get('headers', {}).get('content-type', '') or event.get('headers', {}).get('Content-Type', '')
    
    if 'application/x-www-form-urlencoded' in content_type:
        # Twilio sends form-encoded data
        from urllib.parse import parse_qs
        body = parse_qs(body_raw)
        # Convert lists to single values
        body = {k: v[0] if len(v) == 1 else v for k, v in body.items()}
    else:
        # Try to parse as JSON
        try:
            if isinstance(body_raw, str):
                body = json.loads(body_raw) if body_raw else {}
            else:
                body = body_raw
        except:
            body = {}
    
    # Also check query string parameters (Twilio might send call_id here)
    query_params = event.get('queryStringParameters', {}) or {}
    body.update(query_params)
    
    # Route to appropriate handler (handle both /voice and /prod/voice)
    if '/initiate-call' in path or '/api/call/initiate' in path:
        return handle_initiate_call(body)
    elif '/voice' in path:
        return handle_voice_webhook(body)
    elif '/status' in path:
        return handle_status_callback(body)
    else:
        return {
            'statusCode': 404,
            'body': json.dumps({'error': 'Not found', 'path': path})
        }


def handle_initiate_call(payload):
    """Initiate a new call via Twilio"""
    
    try:
        vendor_name = payload.get('vendor_name')
        call_type = payload.get('call_type', 'place_order')
        context = payload.get('context', {})
        phone_number = payload.get('phone_number')
        
        if not vendor_name:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'vendor_name is required'})
            }
        
        # Call AgentCore agent to generate script
        print(f"Calling AgentCore agent: {AGENTCORE_AGENT_ARN}")
        
        agentcore_response = bedrock_agentcore.invoke_agent_runtime(
            agentRuntimeArn=AGENTCORE_AGENT_ARN,
            qualifier='DEFAULT',
            payload=json.dumps({
                'vendor_name': vendor_name,
                'call_type': call_type,
                'context': context,
                'phone_number': phone_number
            })
        )
        
        # Parse AgentCore response
        response_body = agentcore_response['response']
        agent_result = json.loads(response_body.read())
        
        if agent_result.get('status') != 'success':
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'Failed to generate call script',
                    'details': agent_result
                })
            }
        
        call_id = agent_result['call_id']
        script = agent_result['script']
        phone = agent_result['phone_number']
        
        # Store script in DynamoDB for TwiML handler to retrieve
        table = dynamodb.Table('vendor-call-logs')
        table.update_item(
            Key={'call_id': call_id},
            UpdateExpression='SET script = :script, phone_number = :phone',
            ExpressionAttributeValues={
                ':script': script,
                ':phone': phone
            }
        )
        
        # Initiate Twilio call
        if not twilio_client:
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'status': 'success',
                    'message': 'Script generated but Twilio not configured',
                    'call_id': call_id,
                    'script': script
                })
            }
        
        # Get API Gateway URL from environment
        api_url = os.environ.get('API_GATEWAY_URL', 'https://your-api-gateway-url')
        
        # Make the call
        call = twilio_client.calls.create(
            to=phone,
            from_=TWILIO_PHONE_NUMBER,
            url=f"{api_url}/voice?call_id={call_id}",
            method='POST',
            status_callback=f"{api_url}/status?call_id={call_id}",
            record=True
        )
        
        # Update call log with Twilio SID
        table.update_item(
            Key={'call_id': call_id},
            UpdateExpression='SET twilio_call_sid = :sid, call_status = :status',
            ExpressionAttributeValues={
                ':sid': call.sid,
                ':status': 'initiated'
            }
        )
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'status': 'success',
                'call_id': call_id,
                'twilio_call_sid': call.sid,
                'phone_number': phone,
                'message': f'Call initiated to {vendor_name}'
            })
        }
        
    except Exception as e:
        print(f"Error initiating call: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'traceback': traceback.format_exc()
            })
        }


def handle_voice_webhook(params):
    """Generate TwiML response for Twilio call"""
    
    try:
        print(f"Voice webhook params: {json.dumps(params, default=str)}")
        call_id = params.get('call_id')
        
        if not call_id:
            print("No call_id provided, using fallback TwiML")
            # Fallback TwiML
            response = VoiceResponse()
            response.say("Hello, this is HeartKart calling. Please contact us at your convenience.")
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/xml'},
                'body': str(response)
            }
        
        print(f"Looking up call_id: {call_id}")
        
        # Get script from DynamoDB
        table = dynamodb.Table('vendor-call-logs')
        result = table.get_item(Key={'call_id': call_id})
        
        print(f"DynamoDB result: {json.dumps(result, default=str)}")
        
        if 'Item' not in result:
            print("No item found in DynamoDB")
            response = VoiceResponse()
            response.say("Call script not found. Please contact us directly.")
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/xml'},
                'body': str(response)
            }
        
        script = result['Item'].get('script', 'Hello, this is HeartKart calling.')
        print(f"Retrieved script: {script[:100]}...")
        
        # Generate TwiML with pauses between sentences
        # Split script into sentences and add pauses for natural speech flow
        response = VoiceResponse()
        
        # Split by sentence endings (. ! ?) - use lookahead to keep punctuation with sentence
        # This pattern matches sentence endings followed by space or end of string
        sentence_pattern = r'([.!?]+)\s+'
        chunks = re.split(sentence_pattern, script)
        
        # Recombine sentences with their punctuation
        sentences = []
        for i in range(0, len(chunks) - 1, 2):
            if i + 1 < len(chunks):
                sentence = chunks[i] + chunks[i + 1]
                if sentence.strip():
                    sentences.append(sentence.strip())
        
        # Add the last chunk if it exists and wasn't part of a pair
        if len(chunks) % 2 == 1 and chunks[-1].strip():
            sentences.append(chunks[-1].strip())
        
        # If no sentences found (no punctuation), split by commas or use whole script
        if not sentences:
            # Try splitting by commas as a fallback
            comma_chunks = [c.strip() for c in script.split(',') if c.strip()]
            if len(comma_chunks) > 1:
                sentences = comma_chunks
            else:
                sentences = [script]
        
        # Add each sentence with appropriate pauses
        # Look for "thank you" sentences to add a 5-second pause before them
        for i, sentence in enumerate(sentences):
            if sentence.strip():
                # Check if this sentence contains "thank" (case-insensitive)
                is_thank_you = re.search(r'\b(thank|thanks|thank you)\b', sentence, re.IGNORECASE)
                
                # Check if next sentence is a thank you (to skip 1-sec pause before it)
                next_is_thank_you = False
                if i < len(sentences) - 1:
                    next_sentence = sentences[i + 1]
                    next_is_thank_you = bool(re.search(r'\b(thank|thanks|thank you)\b', next_sentence, re.IGNORECASE))
                
                # If this is a thank you sentence and it's not the first sentence,
                # add a 5-second pause before it (after PO details)
                if is_thank_you and i > 0:
                    response.pause(length=5)
                
                response.say(sentence, voice='Polly.Joanna', language='en-US')
                
                # Add a 1-second pause after each sentence except:
                # - The last sentence
                # - If the next sentence is a thank you (we'll add 5-sec pause before that instead)
                if i < len(sentences) - 1 and not next_is_thank_you:
                    response.pause(length=1)
        
        twiml = str(response)
        print(f"Generated TwiML: {twiml[:200]}...")
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/xml'},
            'body': twiml
        }
        
    except Exception as e:
        print(f"Error generating TwiML: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        
        # Fallback TwiML
        response = VoiceResponse()
        response.say("We're experiencing technical difficulties. Please contact us directly.")
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/xml'},
            'body': str(response)
        }


def handle_status_callback(params):
    """Handle Twilio call status updates"""
    
    try:
        call_sid = params.get('CallSid')
        call_status = params.get('CallStatus')
        
        print(f"Call {call_sid} status: {call_status}")
        
        # Update DynamoDB
        table = dynamodb.Table('vendor-call-logs')
        
        # Find call by Twilio SID
        response = table.scan(
            FilterExpression='twilio_call_sid = :sid',
            ExpressionAttributeValues={':sid': call_sid}
        )
        
        if response['Items']:
            call_id = response['Items'][0]['call_id']
            table.update_item(
                Key={'call_id': call_id},
                UpdateExpression='SET call_status = :status, updated_at = :time',
                ExpressionAttributeValues={
                    ':status': call_status,
                    ':time': datetime.now().isoformat()
                }
            )
        
        return {
            'statusCode': 200,
            'body': json.dumps({'status': 'updated'})
        }
        
    except Exception as e:
        print(f"Error updating status: {e}")
        return {
            'statusCode': 200,
            'body': json.dumps({'status': 'error', 'error': str(e)})
        }
