"""
Notification Creator
Creates notifications for the frontend when orders are placed.

For successful vendor calls, this also generates a vendor-ready PO PDF
and exposes it via a URL that the NotificationsPanel can open.
"""

from datetime import datetime
from typing import Dict, Any
import os

from currency_utils import usd_to_inr

# Support both package and script-style imports
try:
    from .po_pdf_generator import generate_vendor_po_pdf
except ImportError:
    from po_pdf_generator import generate_vendor_po_pdf


def create_notification(po: Dict[str, Any], vendor: Dict[str, Any],
                       email_draft: Dict[str, Any], call_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a notification for the frontend notifications panel
    
    Args:
        po: Purchase order details
        vendor: Vendor information
        email_draft: Drafted email
        call_result: Call result with transcript
        
    Returns:
        Notification object for frontend
    """
    now_iso = datetime.now().isoformat()

    # Infer a primary product name from the PO for grouping/deduping in the UI.
    items = po.get('items') or []
    primary_product_name = ''
    if items and isinstance(items, list):
        first = items[0] or {}
        primary_product_name = first.get('name') or first.get('sku') or ''

    # Compute INR amount for display while keeping stored PO amounts in USD.
    total_amount_usd = po.get('total_amount', 0)
    total_amount_inr = usd_to_inr(total_amount_usd)
    
    # Try to generate a PDF and compute a URL for it
    pdf_url = ''
    try:
        pdf_bytes = generate_vendor_po_pdf(po)
        
        # Determine output directory (shared with Flask app)
        pdf_dir = os.getenv(
            'PO_PDF_DIR',
            os.path.join(os.path.dirname(__file__), '..', '..', 'generated_pos')
        )
        pdf_dir = os.path.abspath(pdf_dir)
        os.makedirs(pdf_dir, exist_ok=True)
        
        pdf_path = os.path.join(pdf_dir, f"{po['po_number']}.pdf")
        with open(pdf_path, 'wb') as f:
            f.write(pdf_bytes)
        
        api_url = os.getenv('API_URL', 'http://localhost:5000')
        # Match the Flask route defined in app_agents.py:
        # @app.route('/api/po-pdfs/<po_number>.pdf', methods=['GET'])
        pdf_url = f"{api_url.rstrip('/')}/api/po-pdfs/{po['po_number']}.pdf"
        print(f"   ✅ PO PDF generated at {pdf_path}")
        print(f"   🔗 PDF URL: {pdf_url}")
    except Exception as e:
        # If PDF generation fails, we still return a valid notification
        print(f"⚠️  Error generating PO PDF: {e}")
    
    notification = {
        # Core identifier
        'id': f"notif-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        
        # High-level notification info (for possible future views)
        'type': 'vendor_call_success',
        'timestamp': now_iso,
        'title': f"✅ Order Confirmed: {vendor['name']}",
        'message': f"Successfully placed order with {vendor['name']} for PO {po['po_number']}",
        
        # Fields expected by NotificationsPanel (PendingEmail shape)
        'po_number': po['po_number'],
        'vendor_name': vendor['name'],
        'product_name': primary_product_name,
        'call_sid': call_result.get('call_sid', ''),
        'call_duration': call_result.get('duration', 0) or 0,
        'subject': email_draft.get('subject', ''),
        'body': email_draft.get('body', ''),
        'pdf_url': email_draft.get('pdf_url', '') or pdf_url,
        'created_at': email_draft.get('generated_at', now_iso),
        'status': 'pending',  # NotificationsPanel maps anything not 'sent'/'failed' to 'pending'
        
        # Extra metadata for richer displays
        'vendor_phone': vendor.get('phone', ''),
        # Keep the raw USD amount for internal consistency, but also include an INR
        # field so the frontend can display rupees without re‑implementing logic.
        'total_amount': total_amount_usd,
        'total_amount_inr': total_amount_inr,
        'currency': po.get('currency', 'USD'),
        'display_currency': 'INR',
        'delivery_date': po['delivery_date'],
        'items_count': len(po.get('items', [])),
        'priority': 'high',
        # Order status for frontend semantics:
        # - 'pending_email' until manager clicks "Send Email"
        # - Frontend can treat 'placed' only after email is sent.
        'order_status': 'pending_email',
        'actions': [
            {
                'label': 'Send Email',
                'action': 'send_email',
                'email_draft': email_draft
            },
            {
                'label': 'View PO',
                'action': 'view_po',
                'po_number': po['po_number']
            },
            {
                'label': 'View Transcript',
                'action': 'view_transcript',
                'transcript': call_result.get('transcript', '')
            }
        ],
        'metadata': {
            'call_transcript': call_result.get('transcript', ''),
            'decision_confidence': call_result.get('confidence', 0),
            'attempt_number': call_result.get('attempt_number', 1),
            'po_details': po,
            'email_subject': email_draft.get('subject', ''),
            'email_body': email_draft.get('body', '')
        }
    }
    
    return notification


def create_rejection_notification(vendor: Dict[str, Any], product_info: Dict[str, Any],
                                  order_details: Dict[str, Any], call_result: Dict[str, Any],
                                  rejection_reason: str = '') -> Dict[str, Any]:
    """
    Create a notification when a single vendor rejects the order.
    No PO or email is generated — just an informational rejection card.

    Args:
        vendor: Vendor information
        product_info: Product details
        order_details: Order details
        call_result: Call result with transcript and reasoning
        rejection_reason: Extracted reason the vendor gave (e.g. 'no stock')

    Returns:
        Notification object for frontend
    """
    now_iso = datetime.now().isoformat()
    vendor_name = vendor.get('name', 'Vendor')
    product_name = product_info.get('name', 'Product')

    if not rejection_reason:
        rejection_reason = call_result.get('reasoning', '') or 'Vendor declined the order'

    notification = {
        'id': f"notif-reject-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        'type': 'vendor_call_rejection',
        'timestamp': now_iso,
        'title': f"Vendor Rejected: {vendor_name}",
        'message': f"{vendor_name} rejected the order for {product_name}. Reason: {rejection_reason}",

        # PendingEmail-compatible shape (no email/PO content)
        'po_number': 'N/A',
        'vendor_name': vendor_name,
        'product_name': product_name,
        'call_sid': call_result.get('call_sid', ''),
        'call_duration': call_result.get('duration', 0) or 0,
        'subject': f"Vendor Rejected: {vendor_name} - {rejection_reason}",
        'body': (
            f"Vendor {vendor_name} was contacted for {product_name} "
            f"(qty: {order_details.get('quantity', 0)}) but declined the order.\n\n"
            f"Rejection reason: {rejection_reason}\n\n"
            f"The system is automatically contacting the next available vendor."
        ),
        'pdf_url': '',
        'created_at': now_iso,
        'status': 'failed',
        'order_status': 'rejected',
        'priority': 'high',
        'rejection_reason': rejection_reason,
        'actions': [
            {
                'label': 'View Call Log',
                'action': 'view_call_logs'
            }
        ],
        'metadata': {
            'call_transcript': call_result.get('transcript', ''),
            'decision_confidence': call_result.get('confidence', 0),
            'attempt_number': call_result.get('attempt_number', 1),
            'product_info': product_info,
            'order_details': order_details,
        }
    }

    return notification


def create_failure_notification(product_info: Dict[str, Any], order_details: Dict[str, Any],
                                attempts: list) -> Dict[str, Any]:
    """
    Create notification when all vendors decline
    
    Args:
        product_info: Product information
        order_details: Order details
        attempts: List of all call attempts
        
    Returns:
        Notification object for frontend
    """
    vendors_tried = [attempt.get('vendor_name', 'Unknown') for attempt in attempts]

    # Choose a safe vendor label for the failure card:
    # - If exactly one vendor was tried, show that name.
    # - If multiple vendors were tried, use a generic label to avoid confusion.
    if len(vendors_tried) == 1:
        header_vendor_name = vendors_tried[0]
    elif len(vendors_tried) > 1:
        header_vendor_name = "Multiple vendors"
    else:
        header_vendor_name = "Vendor"

    # Try to use the last attempt's call details for the call log button
    last_attempt = attempts[-1] if attempts else {}
    call_sid = last_attempt.get('call_sid', '') or ''
    duration = last_attempt.get('duration', 0) or 0
    last_transcript = last_attempt.get('transcript', '') or ''

    now_iso = datetime.now().isoformat()

    notification = {
        # Core identifier
        'id': f"notif-{datetime.now().strftime('%Y%m%d-%H%M%S')}",

        # High-level notification info
        'type': 'vendor_call_failure',
        'timestamp': now_iso,
        'title': f"❌ Order Not Placed: {product_info.get('name', 'Product')}",
        'message': 'Vendor did not accept the order. Please review the call log and decide next steps.',

        # Fields aligned with NotificationsPanel (PendingEmail shape)
        # Many of these are placeholders but keep the shape consistent so UI logic stays simple.
        'po_number': 'N/A',
        'vendor_name': header_vendor_name,
        'call_sid': call_sid,
        'call_duration': duration,
        'subject': f"Vendor did not accept order for {product_info.get('name', 'Product')}",
        'body': (
            f"None of the contacted vendors accepted the order for "
            f"{product_info.get('name', 'Product')} (qty: {order_details.get('quantity', 0)}).\n\n"
            f"Vendors tried: {', '.join(vendors_tried) or 'N/A'}.\n"
            "Please review the call transcript and consider alternative vendors or adjusting the order."
        ),
        'pdf_url': '',
        'created_at': now_iso,
        # Use 'failed' so the frontend can show an 'order not placed' state.
        'status': 'failed',

        # Extra metadata for richer displays
        'product_name': product_info.get('name', 'Product'),
        'quantity': order_details.get('quantity', 0),
        'vendors_tried': vendors_tried,
        'priority': 'urgent',
        'order_status': 'not_placed',
        'actions': [
            {
                'label': 'View Call Log',
                'action': 'view_call_logs'
            },
            {
                'label': 'Find Alternative Vendors',
                'action': 'search_vendors'
            },
            {
                'label': 'Adjust Order',
                'action': 'modify_order'
            },
        ],
        'metadata': {
            # Keep the full attempts list so the UI (or future tools) can inspect
            # every vendor call, and also surface the last transcript directly so
            # the NotificationsPanel can show it even if /api/get-transcript is
            # temporarily unavailable.
            'attempts': attempts,
            'product_info': product_info,
            'order_details': order_details,
            'call_transcript': last_transcript,
        }
    }

    return notification


def format_notification_for_display(notification: Dict[str, Any]) -> str:
    """Format notification as readable text"""
    lines = [
        "=" * 70,
        notification['title'],
        "=" * 70,
        "",
        f"Time: {notification['timestamp'][:19]}",
        f"Type: {notification['type']}",
        f"Priority: {notification['priority'].upper()}",
        "",
        notification['message'],
        ""
    ]
    
    if notification['type'] == 'vendor_call_success':
        total_amount_usd = notification.get('total_amount', 0)
        total_amount_inr = usd_to_inr(total_amount_usd)

        lines.extend([
            "ORDER DETAILS:",
            f"  PO Number: {notification['po_number']}",
            f"  Vendor: {notification['vendor_name']}",
            f"  Total: ₹{total_amount_inr:.2f}",
            f"  Delivery: {notification['delivery_date']}",
            f"  Items: {notification['items_count']}",
            "",
            "ACTIONS REQUIRED:",
            "  1. Review and send confirmation email to vendor",
            "  2. Download and file purchase order",
            "  3. Update inventory system"
        ])
    elif notification['type'] == 'vendor_call_failure':
        lines.extend([
            "VENDORS TRIED:",
        ])
        for vendor in notification['vendors_tried']:
            lines.append(f"  - {vendor}")
        lines.extend([
            "",
            "ACTIONS REQUIRED:",
            "  1. Search for alternative vendors",
            "  2. Consider adjusting order quantity or specifications",
            "  3. Review call transcripts for insights"
        ])
    
    lines.append("=" * 70)
    
    return '\n'.join(lines)


if __name__ == '__main__':
    # Test notification creation
    test_po = {
        'po_number': 'PO-20241120-001',
        'total_amount': 2600.00,
        'delivery_date': '2025-12-15',
        'items': [
            {'name': 'Red Ornaments', 'quantity': 300},
            {'name': 'Gold Ornaments', 'quantity': 200}
        ]
    }
    
    test_vendor = {
        'name': 'Holiday Supplies Inc',
        'phone': '+1-555-0123'
    }
    
    test_email = {
        'subject': 'Purchase Order PO-20241120-001',
        'body': 'Please find attached...'
    }
    
    test_call = {
        'call_sid': 'CA1234567890',
        'duration': 45,
        'transcript': 'Agent: Can you fulfill this? Vendor: Yes!',
        'confidence': 0.95,
        'attempt_number': 1
    }
    
    # Test success notification
    print("SUCCESS NOTIFICATION:")
    print()
    notification = create_notification(test_po, test_vendor, test_email, test_call)
    print(format_notification_for_display(notification))
    print()
    print()
    
    # Test failure notification
    print("FAILURE NOTIFICATION:")
    print()
    test_product = {'name': 'Valentine Ornaments'}
    test_order = {'quantity': 500}
    test_attempts = [
        {'vendor_name': 'Vendor A', 'decision': 'NO'},
        {'vendor_name': 'Vendor B', 'decision': 'NO'}
    ]
    
    failure_notif = create_failure_notification(test_product, test_order, test_attempts)
    print(format_notification_for_display(failure_notif))
