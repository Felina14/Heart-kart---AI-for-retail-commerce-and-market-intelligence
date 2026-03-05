"""
Purchase Order Generator
Creates PO when vendor accepts order.

All monetary values are internally stored in USD for calculations, but we
also compute INR equivalents for display purposes using currency_utils.
"""

from datetime import datetime
from typing import Dict, Any, List

from currency_utils import usd_to_inr


def generate_purchase_order(
    vendor: Dict[str, Any],
    product_info: Dict[str, Any],
    order_details: Dict[str, Any],
    call_transcript: str = "",
) -> Dict[str, Any]:
    """
    Generate a purchase order after vendor accepts
    
    Args:
        vendor: Vendor information
        product_info: Product details
        order_details: Order details
        call_transcript: Optional call transcript for reference
        
    Returns:
        PO dictionary with all details
    """
    # Generate PO number
    po_number = f"PO-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    # Extract items
    items = order_details.get("items", [])

    # If no items provided, create from product_info
    if not items:
        total_amount_usd = order_details.get("total_amount", 0)
        quantity = max(order_details.get("quantity", 1), 1)
        unit_price_usd = total_amount_usd / quantity

        items = [
            {
                "name": product_info.get("name", "Product"),
                "sku": product_info.get("sku", "UNKNOWN"),
                "quantity": order_details.get("quantity", 0),
                "unit_price": unit_price_usd,
                "total": total_amount_usd,
            }
        ]

    # Calculate totals
    subtotal = sum(
        item.get("total", item.get("quantity", 0) * item.get("unit_price", 0)) for item in items
    )
    
    # Check if a total_amount was provided that differs from subtotal (e.g. includes tax/shipping)
    provided_total = order_details.get("total_amount", 0)
    if provided_total > subtotal:
        tax = provided_total - subtotal
        total = provided_total
    else:
        tax = 0.0
        total = subtotal

    # Compute INR equivalents for display (kept alongside USD values)
    subtotal_inr = usd_to_inr(subtotal)
    tax_inr = usd_to_inr(tax)
    total_inr = usd_to_inr(total)

    # Create PO
    po = {
        "po_number": po_number,
        "date": datetime.now().isoformat(),
        "vendor": {
            "name": vendor.get("name", "Unknown Vendor"),
            "phone": vendor.get("phone", ""),
            "email": vendor.get("email", ""),
            "address": vendor.get("address", "TBD"),
        },
        "buyer": {
            "company": "HeartKart",
            "contact": "Sarah Johnson",
            "email": "procurement@heartkart.com",
            "phone": "+1-555-0100",
        },
        "items": items,
        # Stored in USD for internal calculations
        "subtotal": subtotal,
        "tax": tax,
        "total_amount": total,
        "currency": "USD",
        # Convenience INR fields for display
        "subtotal_inr": subtotal_inr,
        "tax_inr": tax_inr,
        "total_amount_inr": total_inr,
        "display_currency": "INR",
        "delivery_date": order_details.get("delivery_date", "as soon as possible"),
        "payment_terms": "Net 30",
        "shipping_method": "Standard Ground",
        "notes": f"Order confirmed via phone call on {datetime.now().strftime('%Y-%m-%d')}",
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "call_transcript_summary": _summarize_transcript(call_transcript)
        if call_transcript
        else None,
    }
    
    return po


def _summarize_transcript(transcript: str, max_length: int = 200) -> str:
    """Create a brief summary of the call transcript"""
    if not transcript:
        return None
    
    # Take first few lines or characters
    lines = transcript.split('\n')
    summary_lines = []
    total_length = 0
    
    for line in lines:
        if total_length + len(line) > max_length:
            break
        summary_lines.append(line)
        total_length += len(line)
    
    summary = '\n'.join(summary_lines)
    
    if len(transcript) > max_length:
        summary += '\n... (truncated)'
    
    return summary


def format_po_for_display(po: Dict[str, Any]) -> str:
    """Format PO as readable text"""
    lines = [
        "=" * 70,
        f"PURCHASE ORDER: {po['po_number']}",
        "=" * 70,
        "",
        f"Date: {po['date'][:10]}",
        f"Delivery Date: {po['delivery_date']}",
        "",
        "VENDOR:",
        f"  {po['vendor']['name']}",
        f"  {po['vendor']['phone']}",
        f"  {po['vendor']['email']}",
        "",
        "BUYER:",
        f"  {po['buyer']['company']}",
        f"  {po['buyer']['contact']}",
        f"  {po['buyer']['email']}",
        "",
        "ITEMS:",
        "-" * 70
    ]

    for item in po['items']:
        quantity = item.get('quantity', 0)
        unit_price_usd = item.get('unit_price', 0)
        total_usd = item.get('total', quantity * unit_price_usd)

        unit_price_inr = usd_to_inr(unit_price_usd)
        total_inr = usd_to_inr(total_usd)

        lines.append(f"  {item['name']}")
        lines.append(f"    SKU: {item.get('sku', 'N/A')}")
        lines.append(f"    Quantity: {quantity} @ ₹{unit_price_inr:.2f} each")
        lines.append(f"    Total: ₹{total_inr:.2f}")
        lines.append("")

    subtotal = po.get('subtotal', 0)
    total = po.get('total_amount', 0)

    subtotal_inr = usd_to_inr(subtotal)
    total_inr = usd_to_inr(total)

    lines.extend([
        "-" * 70,
        f"Subtotal: ₹{subtotal_inr:.2f}",
        f"TOTAL: ₹{total_inr:.2f}",
        "",
        f"Payment Terms: {po['payment_terms']}",
        f"Shipping: {po['shipping_method']}",
        "",
        f"Notes: {po['notes']}",
        "=" * 70
    ])
    
    return '\n'.join(lines)


if __name__ == '__main__':
    # Test PO generation
    test_vendor = {
        'name': 'Holiday Supplies Inc',
        'phone': '+1-555-0123',
        'email': 'orders@holidaysupplies.com'
    }
    
    test_product = {
        'name': 'Valentine Ornaments',
        'sku': 'ORN-001'
    }
    
    test_order = {
        'items': [
            {'name': 'Red Ornaments', 'sku': 'ORN-001-R', 'quantity': 300, 'unit_price': 5.00, 'total': 1500.00},
            {'name': 'Gold Ornaments', 'sku': 'ORN-001-G', 'quantity': 200, 'unit_price': 5.50, 'total': 1100.00}
        ],
        'quantity': 500,
        'delivery_date': '2025-12-15',
        'total_amount': 2600.00
    }
    
    test_transcript = """
Agent: Can you fulfill this order?
Vendor: Yes, we can do that.
Agent: Great, thank you!
"""
    
    po = generate_purchase_order(test_vendor, test_product, test_order, test_transcript)
    
    print(format_po_for_display(po))
