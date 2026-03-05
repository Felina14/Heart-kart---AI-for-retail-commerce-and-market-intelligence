"""
Email Drafter Agent for AWS Bedrock AgentCore Runtime (Strands Framework)

AI-powered email drafting agent that generates professional purchase order emails
based on call transcripts and order details. Uses the Strands framework with
@tool decorators for all key data operations.
"""

import json
import os
import re
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional

import boto3
from strands import tool, Agent
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# Initialize AgentCore App
app = BedrockAgentCoreApp()

# Initialize AWS clients
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# Import product data access layer
from product_data_access import get_all_products, get_product_by_sku

# Currency conversion (USD stored internally → INR for display)
USD_TO_INR_RATE = float(os.getenv('USD_TO_INR', '89.6'))


def usd_to_inr(amount_usd: float) -> float:
    """Convert USD to INR."""
    try:
        return round(float(amount_usd) * USD_TO_INR_RATE, 2)
    except Exception:
        return 0.0


# ============================================================================
# STRANDS TOOLS
# ============================================================================

@tool
def get_vendor_contact_info(vendor_name: str) -> Dict:
    """
    Look up vendor contact information from the products database.

    Args:
        vendor_name: Name of the vendor to look up

    Returns:
        Dict with vendor_name, contact_person, email, phone, address,
        and payment_terms.
    """
    try:
        products = get_all_products(limit=1000)
        for product in products:
            vname = product.get('vendor_name', '')
            if vname and vendor_name.lower() in vname.lower():
                return {
                    'vendor_name': vname,
                    'contact_person': product.get('vendor_contact', 'Purchasing Manager'),
                    'email': product.get('vendor_email', f"orders@{vname.lower().replace(' ', '')}.com"),
                    'phone': product.get('vendor_phone', ''),
                    'address': product.get('vendor_address', ''),
                    'payment_terms': product.get('payment_terms', 'Net 30'),
                }

        return {
            'vendor_name': vendor_name,
            'contact_person': 'Purchasing Manager',
            'email': f"orders@{vendor_name.lower().replace(' ', '')}.com",
            'phone': '',
            'address': '',
            'payment_terms': 'Net 30',
        }
    except Exception as e:
        print(f"Error looking up vendor: {e}")
        return {
            'vendor_name': vendor_name,
            'contact_person': 'Purchasing Manager',
            'email': '',
            'phone': '',
            'address': '',
            'payment_terms': 'Net 30',
        }


@tool
def get_product_details_for_po(sku: str) -> Dict:
    """
    Get product details needed for a purchase order line item.

    Args:
        sku: Product SKU identifier

    Returns:
        Dict with sku, name, category, price (USD), price_inr, vendor_name.
    """
    try:
        product = get_product_by_sku(sku)
        if not product:
            return {'error': f'Product {sku} not found'}
        price_usd = float(product.get('price', 0))
        return {
            'sku': sku,
            'name': product.get('name', ''),
            'category': product.get('category', ''),
            'price_usd': price_usd,
            'price_inr': usd_to_inr(price_usd),
            'vendor_name': product.get('vendor_name', ''),
        }
    except Exception as e:
        print(f"Error getting product details for {sku}: {e}")
        return {'error': str(e)}


@tool
def get_recent_call_transcript(vendor_name: str) -> Dict:
    """
    Look up the most recent call transcript for a vendor from the call logs table.

    Args:
        vendor_name: Name of the vendor whose call transcript to retrieve

    Returns:
        Dict with call_sid, vendor_name, transcript, decision, call_date.
    """
    try:
        call_logs_table = dynamodb.Table('heartkart-call-logs')
        response = call_logs_table.scan(
            FilterExpression='contains(vendor_name, :vname)',
            ExpressionAttributeValues={':vname': vendor_name},
            Limit=5,
        )
        items = response.get('Items', [])
        if items:
            items.sort(key=lambda x: x.get('call_date', ''), reverse=True)
            latest = items[0]
            return {
                'call_sid': latest.get('call_sid', ''),
                'vendor_name': latest.get('vendor_name', vendor_name),
                'transcript': latest.get('transcript', ''),
                'decision': latest.get('decision', 'UNKNOWN'),
                'call_date': latest.get('call_date', ''),
            }
        return {
            'call_sid': '',
            'vendor_name': vendor_name,
            'transcript': '',
            'decision': 'UNKNOWN',
            'call_date': '',
        }
    except Exception as e:
        print(f"Error fetching call transcript for {vendor_name}: {e}")
        return {
            'call_sid': '',
            'vendor_name': vendor_name,
            'transcript': '',
            'decision': 'UNKNOWN',
            'call_date': '',
        }


# ============================================================================
# EMAIL GENERATION HELPERS
# ============================================================================

def clean_email_body(body: str) -> str:
    """Remove markdown formatting and replace placeholders with actual contact info."""
    # Remove markdown bold
    body = re.sub(r'\*\*([^*]+)\*\*', r'\1', body)
    # Remove markdown italic
    body = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'\1', body)
    # Remove markdown headers
    body = re.sub(r'^#+\s+', '', body, flags=re.MULTILINE)

    placeholders = {
        '[Your Name]': 'Alex Johnson',
        '{Your Name}': 'Alex Johnson',
        '[your name]': 'Alex Johnson',
        'Your Name': 'Alex Johnson',
        '[Your Position]': 'Inventory Manager',
        '{Your Position}': 'Inventory Manager',
        '[Your Company]': 'HeartKart',
        '{Your Company}': 'HeartKart',
        '[Your Contact Information]': 'inventory@heartkart.com\n(555) 123-4567',
        '{Your Contact Information}': 'inventory@heartkart.com\n(555) 123-4567',
        '[Your Email]': 'inventory@heartkart.com',
        '[Your Phone]': '(555) 123-4567',
    }
    for placeholder, replacement in placeholders.items():
        body = body.replace(placeholder, replacement)

    body = re.sub(r'\n{3,}', '\n\n', body)
    return body.strip()


def generate_fallback_email(
    vendor_name: str,
    contact_person: str,
    po_number: str,
    items: List[Dict],
    total_amount: float,
    delivery_date: str,
) -> Dict:
    """Generate a basic email if AI generation fails."""
    items_lines = []
    for item in items:
        unit_price_inr = usd_to_inr(item.get('unit_price', 0))
        items_lines.append(
            f"  • {item.get('name', 'Item')}: {item.get('quantity', 0)} units @ ₹{unit_price_inr:.2f}"
        )
    items_text = "\n".join(items_lines)
    total_amount_inr = usd_to_inr(total_amount)

    body = f"""Dear {contact_person},

I hope this email finds you well.

Following our recent conversation, I'm pleased to submit Purchase Order {po_number} for your review and processing.

Order Details:
{items_text}

Total Amount: ₹{total_amount_inr:.2f}
Requested Delivery Date: {delivery_date}
Payment Terms: Net 30

Please confirm receipt of this order and the expected delivery date at your earliest convenience.

The purchase order is attached for your records.

Thank you for your continued partnership.

Best regards,
Alex Johnson
Inventory Manager
HeartKart
inventory@heartkart.com
(555) 123-4567
"""
    return {
        'subject': f'Purchase Order {po_number} - {vendor_name}',
        'body': body,
        'attachments': [f'{po_number}.pdf'],
        'cc': [],
        'generated_at': datetime.now().isoformat(),
    }


# ============================================================================
# STRANDS AGENT
# ============================================================================

_bedrock_model = BedrockModel(
    model_id=os.getenv("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0"),
    temperature=float(os.getenv("MODEL_TEMPERATURE", "0.7")),
)

agent = Agent(
    model=_bedrock_model,
    tools=[get_vendor_contact_info, get_product_details_for_po, get_recent_call_transcript],
    system_prompt=(
        "You are the HeartKart Email Drafter Agent. Draft professional purchase order emails "
        "for Valentine's Day vendors.\n\n"
        "Use your tools to:\n"
        "1. Look up vendor contact information using get_vendor_contact_info\n"
        "2. Get product details for PO line items using get_product_details_for_po\n"
        "3. Retrieve recent call transcripts using get_recent_call_transcript\n\n"
        "When drafting emails:\n"
        "- Use a professional and friendly tone\n"
        "- Reference phone conversations if applicable\n"
        "- Include all order details clearly\n"
        "- Request confirmation from the vendor\n"
        "- Include payment terms (Net 30)\n"
        "- Sign as Alex Johnson, Inventory Manager, HeartKart\n"
        "- Use plain text, NO markdown formatting\n"
        "- All prices in Indian Rupees (₹)\n"
        "- Do NOT use placeholders — use actual contact details."
    ),
)


# ============================================================================
# MAIN EMAIL DRAFTING FUNCTION
# ============================================================================

def draft_po_email(
    vendor_name: str,
    contact_person: str,
    po_number: str,
    items: List[Dict],
    total_amount: float,
    delivery_date: str,
    call_transcript: Optional[str] = None,
    call_summary: Optional[Dict] = None,
) -> Dict:
    """Draft a professional PO email using the Strands agent, with fallback to direct Bedrock."""
    print(f"📧 Drafting PO email for {vendor_name}...")

    # Build context from call if available
    call_context = ""
    if call_transcript:
        call_context = f"\n\nCall Summary:\n{call_transcript}"
    elif call_summary:
        call_context = (
            f"\n\nCall Summary:\nWe spoke with {contact_person} and "
            f"confirmed the following details."
        )

    # Convert to INR for display
    total_amount_inr = usd_to_inr(total_amount)
    items_text_lines = []
    for item in items:
        unit_price_inr = usd_to_inr(item.get('unit_price', 0))
        items_text_lines.append(
            f"- {item.get('name', 'Item')}: {item.get('quantity', 0)} units @ ₹{unit_price_inr:.2f} each"
        )
    items_text = "\n".join(items_text_lines)

    prompt = f"""Draft a professional purchase order email for the following:

Vendor: {vendor_name}
Contact: {contact_person}
PO Number: {po_number}
Delivery Date: {delivery_date}
Total Amount: ₹{total_amount_inr:.2f} (in Indian rupees)

Items:
{items_text}
{call_context}

Requirements:
1. Professional and friendly tone
2. Clear subject line
3. Reference any phone conversation if applicable
4. Include all order details
5. Request confirmation
6. Include payment terms (Net 30)
7. Sign as Alex Johnson, Inventory Manager, HeartKart, inventory@heartkart.com, (555) 123-4567
8. Thank them for their business
9. Use plain text - NO markdown formatting
10. Do NOT use placeholders

Generate as JSON:
{{"subject": "...", "body": "..."}}
"""

    # Try Strands agent first
    try:
        agent_response = agent(prompt)
        response_text = str(agent_response)

        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            email_data = json.loads(json_match.group())
        else:
            email_data = {
                'subject': f'Purchase Order {po_number} - {vendor_name}',
                'body': response_text,
            }

        if 'body' in email_data:
            email_data['body'] = clean_email_body(email_data['body'])

        email_data['attachments'] = [f'{po_number}.pdf']
        email_data['cc'] = []
        email_data['generated_at'] = datetime.now().isoformat()

        print(f"✅ Email drafted via Strands agent")
        return email_data

    except Exception as e:
        print(f"Strands agent failed: {e}. Trying direct Bedrock call...")

    # Fallback: direct Bedrock call
    try:
        response = bedrock.converse(
            modelId='amazon.nova-pro-v1:0',
            messages=[{'role': 'user', 'content': [{'text': prompt}]}],
            inferenceConfig={'maxTokens': 2000, 'temperature': 0.7, 'topP': 0.9},
        )
        response_text = response['output']['message']['content'][0]['text']

        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            email_data = json.loads(json_match.group())
        else:
            email_data = {
                'subject': f'Purchase Order {po_number} - {vendor_name}',
                'body': response_text,
            }

        if 'body' in email_data:
            email_data['body'] = clean_email_body(email_data['body'])

        email_data['attachments'] = [f'{po_number}.pdf']
        email_data['cc'] = []
        email_data['generated_at'] = datetime.now().isoformat()

        print(f"✅ Email drafted via direct Bedrock call")
        return email_data

    except Exception as e2:
        print(f"Direct Bedrock call failed: {e2}. Using fallback template.")
        return generate_fallback_email(
            vendor_name, contact_person, po_number,
            items, total_amount, delivery_date,
        )


# ============================================================================
# AGENTCORE RUNTIME ENTRY POINT
# ============================================================================

@app.entrypoint
def email_drafter_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    AgentCore Runtime entry point for the Email Drafter Agent.

    Args:
        payload: Input containing vendor_name, contact_person, po_number,
                 items, total_amount, delivery_date, call_transcript, call_summary

    Returns:
        Dictionary with subject, body, attachments, cc, generated_at
    """
    print(f"📧 Email Drafter Agent - Received request: {json.dumps(payload, default=str)}")

    try:
        vendor_name = payload.get('vendor_name', 'Unknown Vendor')
        contact_person = payload.get('contact_person', 'Purchasing Manager')
        po_number = payload.get('po_number', f"PO-{datetime.now().strftime('%Y%m%d-%H%M')}")
        items = payload.get('items', [])
        total_amount = float(payload.get('total_amount', 0))
        delivery_date = payload.get('delivery_date', 'As soon as possible')
        call_transcript = payload.get('call_transcript')
        call_summary = payload.get('call_summary')

        result = draft_po_email(
            vendor_name=vendor_name,
            contact_person=contact_person,
            po_number=po_number,
            items=items,
            total_amount=total_amount,
            delivery_date=delivery_date,
            call_transcript=call_transcript,
            call_summary=call_summary,
        )
        return {'status': 'success', **result}

    except Exception as e:
        import traceback
        print(f"Error in email drafter handler: {e}")
        traceback.print_exc()
        return {'status': 'error', 'error': str(e), 'traceback': traceback.format_exc()}


if __name__ == "__main__":
    app.run()
