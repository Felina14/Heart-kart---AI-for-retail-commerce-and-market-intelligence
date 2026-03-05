#!/usr/bin/env python3
"""
Email Drafter Agent
Drafts professional emails for purchase orders based on call transcripts
"""

import boto3
import json
import re
from datetime import datetime
from typing import Dict, List, Optional

from currency_utils import usd_to_inr

class EmailDrafterAgent:
    """
    AI agent that drafts professional purchase order emails
    """
    
    def __init__(self, region='us-east-1'):
        self.bedrock = boto3.client('bedrock-runtime', region_name=region)
        self.model_id = 'amazon.nova-pro-v1:0'
    
    def draft_po_email(
        self,
        vendor_name: str,
        contact_person: str,
        po_number: str,
        items: List[Dict],
        total_amount: float,
        delivery_date: str,
        call_transcript: Optional[str] = None,
        call_summary: Optional[Dict] = None
    ) -> Dict:
        """
        Draft a professional PO email based on order details and call transcript
        
        Returns:
            {
                'subject': str,
                'body': str,
                'attachments': List[str],
                'cc': List[str]
            }
        """
        
        # Build context from call if available
        call_context = ""
        if call_transcript:
            call_context = f"\n\nCall Summary:\n{call_transcript}"
        elif call_summary:
            call_context = f"\n\nCall Summary:\nWe spoke with {contact_person} and confirmed the following details."
        
        # Convert totals to INR for vendor-facing communication
        total_amount_inr = usd_to_inr(total_amount)

        # Build items list (rendered in INR)
        items_text_lines: List[str] = []
        for item in items:
            unit_price_usd = item.get('unit_price', 0)
            unit_price_inr = usd_to_inr(unit_price_usd)
            items_text_lines.append(
                f"- {item['name']}: {item['quantity']} units @ ₹{unit_price_inr:.2f} each"
            )
        items_text = "\n".join(items_text_lines)
        
        # Create prompt for email generation
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
7. Provide actual contact information (Alex Johnson, Inventory Manager, HeartKart, inventory@heartkart.com, (555) 123-4567)
8. Thank them for their business
9. Use plain text format - NO markdown formatting (no ** for bold, no # for headers)
10. Do NOT use placeholders like [Your Name] or {{Your Contact Information}} - use actual values

Generate:
1. Email subject line
2. Email body (professional format)

Format as JSON:
{{
    "subject": "...",
    "body": "..."
}}
"""
        
        # Call Nova Pro to generate email
        try:
            response = self.bedrock.converse(
                modelId=self.model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": prompt}]
                    }
                ],
                inferenceConfig={
                    "maxTokens": 2000,
                    "temperature": 0.7,
                    "topP": 0.9
                }
            )
            
            # Extract response
            response_text = response['output']['message']['content'][0]['text']
            
            # Parse JSON response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                email_data = json.loads(json_match.group())
            else:
                email_data = {
                    'subject': f'Purchase Order {po_number} - {vendor_name}',
                    'body': response_text
                }
            
            # Clean up email body
            if 'body' in email_data:
                email_data['body'] = self._clean_email_body(email_data['body'])
            
            # Add metadata
            email_data['attachments'] = [f'{po_number}.pdf']
            email_data['cc'] = []
            email_data['generated_at'] = datetime.now().isoformat()
            
            return email_data
            
        except Exception as e:
            print(f"Error generating email: {e}")
            return self._generate_fallback_email(
                vendor_name, contact_person, po_number,
                items, total_amount, delivery_date
            )
    
    def _clean_email_body(self, body: str) -> str:
        """
        Clean up email body by:
        1. Removing markdown formatting (** for bold, etc.)
        2. Replacing placeholder text with actual contact information
        """
        # Remove markdown bold formatting (**text** -> text)
        body = re.sub(r'\*\*([^*]+)\*\*', r'\1', body)
        # Remove markdown italic formatting (*text* -> text)
        body = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'\1', body)
        # Remove markdown headers (# Header -> Header)
        body = re.sub(r'^#+\s+', '', body, flags=re.MULTILINE)
        
        # Replace placeholders with actual contact information
        contact_info = {
            '[Your Name]': 'Alex Johnson',
            '{Your Name}': 'Alex Johnson',
            '[your name]': 'Alex Johnson',
            '{your name}': 'Alex Johnson',
            'Your Name': 'Alex Johnson',
            'your name here': 'Alex Johnson',
            
            '[Your Position]': 'Inventory Manager',
            '{Your Position}': 'Inventory Manager',
            '[your position]': 'Inventory Manager',
            '{your position}': 'Inventory Manager',
            'Your Position': 'Inventory Manager',
            
            '[Your Company]': 'HeartKart',
            '{Your Company}': 'HeartKart',
            '[your company]': 'HeartKart',
            '{your company}': 'HeartKart',
            'Your Company': 'HeartKart',
            
            '[Your Contact Information]': 'inventory@heartkart.com\n(555) 123-4567',
            '{Your Contact Information}': 'inventory@heartkart.com\n(555) 123-4567',
            '[your contact information]': 'inventory@heartkart.com\n(555) 123-4567',
            '{your contact information}': 'inventory@heartkart.com\n(555) 123-4567',
            'Your Contact Information': 'inventory@heartkart.com\n(555) 123-4567',
            
            '[Your Email]': 'inventory@heartkart.com',
            '[Your Phone]': '(555) 123-4567',
        }
        
        for placeholder, replacement in contact_info.items():
            body = body.replace(placeholder, replacement)
        
        body = re.sub(r'\n{3,}', '\n\n', body)
        
        return body.strip()
    
    def _generate_fallback_email(
        self, vendor_name, contact_person, po_number,
        items, total_amount, delivery_date
    ) -> Dict:
        """Generate a basic email if AI generation fails"""
        
        items_text_lines: List[str] = []
        for item in items:
            unit_price_usd = item.get('unit_price', 0)
            unit_price_inr = usd_to_inr(unit_price_usd)
            items_text_lines.append(
                f"  • {item['name']}: {item['quantity']} units @ ₹{unit_price_inr:.2f}"
            )
        items_text = "\n".join(items_text_lines)

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
            'generated_at': datetime.now().isoformat()
        }


# Test function
if __name__ == '__main__':
    print("🤖 Testing Email Drafter Agent")
    print("=" * 70)
    
    agent = EmailDrafterAgent()
    
    email = agent.draft_po_email(
        vendor_name='Holiday Decor Wholesale',
        contact_person='Sarah Johnson',
        po_number='PO-2024-1234',
        items=[
            {'name': 'Red Glass Ornaments', 'quantity': 100, 'unit_price': 5.50},
            {'name': 'Gold Garland', 'quantity': 50, 'unit_price': 12.00}
        ],
        total_amount=1250.00,
        delivery_date='February 10th, 2026',
        call_summary={'status': 'confirmed', 'notes': 'Stock available, delivery confirmed'}
    )
    
    print("\n📧 Generated Email:")
    print(f"\nSubject: {email['subject']}")
    print(f"\n{email['body']}")
    print(f"\nAttachments: {', '.join(email['attachments'])}")
