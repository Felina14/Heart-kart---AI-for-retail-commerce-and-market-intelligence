"""
Vendor Caller Agent for AWS Bedrock AgentCore Runtime

Orchestrates outbound vendor calls using:
  • Nova Sonic bidirectional streaming (real-time AI voice)
  • Twilio for telephony (outbound calls, WebSocket media streams)
  • Vendor fallback logic (if vendor 1 says NO, auto-call vendor 2)

Architecture (same as nova_sonic_working_perfectly/):
  ┌──────────────┐      ┌─────────────────────────┐      ┌────────────┐
  │  Twilio PSTN │◄────►│ nova_sonic_twilio_server │◄────►│ Nova Sonic │
  │  (vendor     │ mulaw│  (WebSocket bridge)      │ PCM  │ (AI voice) │
  │   phone)     │ 8kHz │  + audio conversion      │16/24k│            │
  └──────────────┘      └─────────────────────────┘      └────────────┘
                                    ▲
                                    │ transcript + decision
                                    ▼
                          ┌───────────────────┐
                          │  agent.py (this)   │
                          │  AgentCore entry   │
                          │  + fallback logic  │
                          │  + Twilio call API │
                          └───────────────────┘

Files in this folder:
  • agent.py                       — AgentCore entrypoint + call orchestration
  • nova_sonic_voice_agent.py      — NovaSonicVendorAgent (bidirectional streaming)
  • nova_sonic_twilio_server.py    — Twilio WebSocket ↔ Nova Sonic bridge
  • make_conversational_call.py    — Standalone call initiation script
  • check_call_status.py           — Standalone call status checker
  • start_server.sh                — Start the WebSocket server
  • requirements.txt               — Python dependencies
"""

import json
import os
import sys
import uuid
import threading
from datetime import datetime
from typing import Dict, List, Any, Optional

import boto3
from dotenv import load_dotenv

# Load environment
for env_path in ['../../.env', '../.env', '.env']:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break

# Import product data access layer
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from product_data_access import get_all_products, get_product_by_sku, get_products_by_category

# Currency conversion
USD_TO_INR_RATE = float(os.getenv('USD_TO_INR', '89.6'))


def usd_to_inr(amount_usd: float) -> float:
    """Convert USD to INR."""
    try:
        return round(float(amount_usd) * USD_TO_INR_RATE, 2)
    except Exception:
        return 0.0


# ======================================================================
# IN-MEMORY STORES
# ======================================================================

# call_metadata_store: call_sid → { vendor_name, contact_person, ... }
call_metadata_store: Dict[str, Dict] = {}

# call_transcripts_store: call_sid → { transcript, decision, ... }
call_transcripts_store: Dict[str, Dict] = {}

# order_chains: order_id → { order_details, vendors_tried, attempt, ... }
order_chains: Dict[str, Dict] = {}


# ======================================================================
# VENDOR LOOKUP
# ======================================================================

def find_alternative_vendor(category: str, vendors_tried: list) -> Optional[Dict]:
    """Find an alternative vendor for a product category, excluding those already tried."""
    try:
        products = get_all_products(limit=1000)
        vendors_tried_lower = [v.lower() for v in vendors_tried]

        # First: try same-category vendors
        for product in products:
            vname = product.get('vendor_name', '')
            cat = product.get('category', '')
            if not vname or vname.lower() in vendors_tried_lower:
                continue
            if category and cat and category.lower() in cat.lower():
                return {
                    'vendor_name': vname,
                    'contact_person': product.get('vendor_contact', 'Purchasing Manager'),
                    'phone_number': product.get('vendor_phone', ''),
                    'category': cat,
                }

        # Second: any vendor not yet tried
        for product in products:
            vname = product.get('vendor_name', '')
            if vname and vname.lower() not in vendors_tried_lower:
                return {
                    'vendor_name': vname,
                    'contact_person': product.get('vendor_contact', 'Purchasing Manager'),
                    'phone_number': product.get('vendor_phone', ''),
                    'category': product.get('category', ''),
                }

        return None
    except Exception as e:
        print(f"Error finding alternative vendor: {e}")
        return None


# ======================================================================
# TWILIO CALL INITIATION
# ======================================================================

def initiate_twilio_call(
    vendor_name: str,
    contact_person: str,
    vendor_phone: str,
    items: List[Dict],
    total_amount: float,
    delivery_date: str,
    order_id: str = None,
    po_number: str = None,
) -> Dict:
    """
    Initiate an outbound Twilio call that connects to the Nova Sonic WebSocket
    server for real-time bidirectional AI voice conversation.

    Returns:
        Dict with call_sid, order_id, status
    """
    try:
        from twilio.rest import Client

        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        from_phone = os.getenv('TWILIO_PHONE_NUMBER')
        ngrok_url = os.getenv('NGROK_URL', '')

        if not all([account_sid, auth_token, from_phone]):
            return {'status': 'error', 'error': 'Twilio credentials not configured'}
        if not ngrok_url:
            return {'status': 'error', 'error': 'NGROK_URL not set — WebSocket server unreachable'}

        if not order_id:
            order_id = str(uuid.uuid4())

        client = Client(account_sid, auth_token)

        # Build TwiML that connects to the Nova Sonic WebSocket server
        ngrok_domain = ngrok_url.replace('https://', '').replace('http://', '')
        websocket_url = f"wss://{ngrok_domain}/media-stream"

        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{websocket_url}" />
    </Connect>
</Response>
"""

        # Place the call
        call = client.calls.create(
            twiml=twiml,
            to=vendor_phone,
            from_=from_phone,
        )

        print(f"✅ Call initiated to {vendor_name} ({vendor_phone})")
        print(f"   Call SID: {call.sid}")
        print(f"   Order ID: {order_id}")

        # Store call metadata so the WebSocket server can look it up
        total_inr = usd_to_inr(total_amount)
        call_metadata_store[call.sid] = {
            'vendor_name': vendor_name,
            'contact_person': contact_person,
            'product_name': ', '.join(item.get('name', 'item') for item in items),
            'quantity': sum(item.get('quantity', 0) for item in items),
            'total_amount': total_amount,
            'total_amount_inr': total_inr,
            'delivery_date': delivery_date,
            'po_number': po_number or f"PO-{datetime.now().strftime('%Y%m%d-%H%M')}",
            'order_id': order_id,
            'call_started_at': datetime.now().isoformat(),
        }

        # Initialize order chain
        if order_id not in order_chains:
            order_chains[order_id] = {
                'order_details': {
                    'items': items,
                    'total_amount': total_amount,
                    'delivery_date': delivery_date,
                    'category': items[0].get('category', '') if items else '',
                },
                'vendors_tried': [vendor_name],
                'attempt_number': 1,
                'max_attempts': 3,
                'status': 'CALLING',
                'current_decision': 'PENDING',
                'call_sids': [call.sid],
            }
        else:
            chain = order_chains[order_id]
            chain['vendors_tried'].append(vendor_name)
            chain['attempt_number'] = len(chain['vendors_tried'])
            chain['status'] = 'CALLING'
            chain['current_decision'] = 'PENDING'
            chain['call_sids'].append(call.sid)

        return {
            'status': 'call_initiated',
            'call_sid': call.sid,
            'order_id': order_id,
            'vendor_name': vendor_name,
            'vendor_phone': vendor_phone,
            'attempt_number': order_chains[order_id]['attempt_number'],
        }

    except Exception as e:
        print(f"❌ Error initiating Twilio call: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'error': str(e)}


# ======================================================================
# VENDOR DECISION + FALLBACK HANDLER
# ======================================================================

def handle_vendor_decision(call_sid: str, decision: str) -> Dict:
    """
    Handle vendor decision after a call completes.
    Called by the WebSocket server via /api/store-transcript.

    If decision == 'NO':
      → Find alternative vendor
      → Automatically initiate fallback call
    """
    meta = call_metadata_store.get(call_sid, {})
    order_id = meta.get('order_id', '')
    vendor_name = meta.get('vendor_name', 'Unknown')

    print(f"📋 Decision for {vendor_name}: {decision} (order_id={order_id})")

    if not order_id or order_id not in order_chains:
        return {'status': 'no_order_chain', 'decision': decision}

    chain = order_chains[order_id]
    chain['current_decision'] = decision

    if decision == 'YES':
        chain['status'] = 'FULFILLED'
        return {
            'status': 'fulfilled',
            'order_id': order_id,
            'fulfilled_by': vendor_name,
            'attempts': chain['attempt_number'],
        }

    elif decision == 'NO':
        if chain['attempt_number'] >= chain['max_attempts']:
            chain['status'] = 'FAILED'
            return {
                'status': 'failed',
                'order_id': order_id,
                'vendors_tried': chain['vendors_tried'],
                'message': f'All {chain["max_attempts"]} vendor attempts exhausted.',
            }

        # Find alternative vendor
        category = chain['order_details'].get('category', '')
        alt_vendor = find_alternative_vendor(category, chain['vendors_tried'])

        if not alt_vendor:
            chain['status'] = 'FAILED'
            return {
                'status': 'failed',
                'order_id': order_id,
                'vendors_tried': chain['vendors_tried'],
                'message': 'No alternative vendors found.',
            }

        # Initiate fallback call
        print(f"🔄 Initiating fallback call to {alt_vendor['vendor_name']}...")
        chain['status'] = 'FALLBACK_IN_PROGRESS'

        result = initiate_twilio_call(
            vendor_name=alt_vendor['vendor_name'],
            contact_person=alt_vendor.get('contact_person', 'Purchasing Manager'),
            vendor_phone=alt_vendor.get('phone_number', ''),
            items=chain['order_details']['items'],
            total_amount=chain['order_details']['total_amount'],
            delivery_date=chain['order_details']['delivery_date'],
            order_id=order_id,
        )

        return {
            'status': 'fallback_initiated',
            'order_id': order_id,
            'previous_vendor': vendor_name,
            'new_vendor': alt_vendor['vendor_name'],
            'attempt': chain['attempt_number'],
            'call_result': result,
        }

    else:  # UNKNOWN
        chain['status'] = 'UNKNOWN'
        return {
            'status': 'unknown',
            'order_id': order_id,
            'vendor_name': vendor_name,
            'message': 'Vendor decision unclear — manual follow-up needed.',
        }


# ======================================================================
# API ENDPOINTS (called by Flask backend or WebSocket server)
# ======================================================================

def get_call_metadata(call_sid: str) -> Dict:
    """Get call metadata for a given call SID (used by WebSocket server)."""
    if call_sid in call_metadata_store:
        meta = call_metadata_store[call_sid]
        return {'success': True, **meta}
    return {'success': False, 'error': f'Call {call_sid} not found'}


def store_transcript(call_sid: str, transcript: str, conversation_history: list, decision: str) -> Dict:
    """
    Store call transcript and trigger vendor fallback if decision is NO.
    Called by the WebSocket server when a call ends.
    """
    # Build formatted transcript from conversation history
    formatted_transcript = transcript
    if not formatted_transcript and conversation_history:
        lines = []
        for msg in conversation_history:
            role = 'AI (Priya)' if msg.get('role') == 'assistant' else 'Vendor'
            content = msg.get('content', '')
            if isinstance(content, list) and content:
                content = content[0].get('text', '')
            lines.append(f"{role}: {content}")
        formatted_transcript = '\n'.join(lines)

    call_transcripts_store[call_sid] = {
        'transcript': formatted_transcript,
        'conversation_history': conversation_history,
        'decision': decision,
        'stored_at': datetime.now().isoformat(),
    }

    print(f"📝 Stored transcript for {call_sid} (decision: {decision})")

    # Handle vendor decision (may trigger fallback call)
    fallback_result = handle_vendor_decision(call_sid, decision)

    return {
        'success': True,
        'call_sid': call_sid,
        'transcript_length': len(formatted_transcript),
        'decision': decision,
        'fallback_result': fallback_result,
    }


# ======================================================================
# AGENTCORE RUNTIME ENTRY POINT
# ======================================================================

try:
    from strands import tool, Agent
    from strands.models import BedrockModel
    from bedrock_agentcore.runtime import BedrockAgentCoreApp

    app = BedrockAgentCoreApp()

    @app.entrypoint
    def vendor_caller_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        AgentCore Runtime entry point for the Vendor Caller Agent.

        Supports actions:
          - 'initiate_call': Start an outbound vendor call via Twilio + Nova Sonic
          - 'handle_decision': Process vendor YES/NO and trigger fallback
          - 'get_metadata': Get call metadata for a call SID
          - 'store_transcript': Store transcript + trigger fallback
          - 'get_order_status': Get order chain status

        The actual voice conversation is handled by:
          nova_sonic_voice_agent.py  (bidirectional streaming)
          nova_sonic_twilio_server.py (WebSocket ↔ Twilio bridge)
        """
        print(f"📞 Vendor Caller Agent — Received request: {json.dumps(payload, default=str)}")

        try:
            action = payload.get('action', 'initiate_call')

            if action == 'initiate_call':
                return initiate_twilio_call(
                    vendor_name=payload.get('vendor_name', 'Unknown Vendor'),
                    contact_person=payload.get('contact_person', 'Purchasing Manager'),
                    vendor_phone=payload.get('vendor_phone', ''),
                    items=payload.get('items', []),
                    total_amount=float(payload.get('total_amount', 0)),
                    delivery_date=payload.get('delivery_date', 'As soon as possible'),
                    order_id=payload.get('order_id'),
                    po_number=payload.get('po_number'),
                )

            elif action == 'handle_decision':
                return handle_vendor_decision(
                    call_sid=payload.get('call_sid', ''),
                    decision=payload.get('decision', 'UNKNOWN'),
                )

            elif action == 'get_metadata':
                return get_call_metadata(payload.get('call_sid', ''))

            elif action == 'store_transcript':
                return store_transcript(
                    call_sid=payload.get('call_sid', ''),
                    transcript=payload.get('transcript', ''),
                    conversation_history=payload.get('conversation_history', []),
                    decision=payload.get('decision', 'UNKNOWN'),
                )

            elif action == 'get_order_status':
                order_id = payload.get('order_id', '')
                if order_id in order_chains:
                    return {'status': 'success', 'order_chain': order_chains[order_id]}
                return {'status': 'error', 'error': f'Order {order_id} not found'}

            else:
                return {'status': 'error', 'error': f'Unknown action: {action}'}

        except Exception as e:
            import traceback
            print(f"Error in vendor caller handler: {e}")
            traceback.print_exc()
            return {'status': 'error', 'error': str(e), 'traceback': traceback.format_exc()}

    AGENTCORE_AVAILABLE = True

except ImportError:
    print("⚠️ AgentCore / Strands not installed — running in standalone mode")
    app = None
    AGENTCORE_AVAILABLE = False


# ======================================================================
# STANDALONE MODE (when run directly, starts the WebSocket server)
# ======================================================================

if __name__ == "__main__":
    if AGENTCORE_AVAILABLE and app:
        print("🚀 Starting Vendor Caller Agent in AgentCore mode...")
        app.run()
    else:
        print("🚀 Starting Vendor Caller Agent in standalone mode...")
        print("   Use nova_sonic_twilio_server.py --websocket to start the WebSocket server")
        print("   Use make_conversational_call.py to initiate a call")
