"""
Simple PDF generator for vendor caller purchase orders.
Creates a clean, single-vendor PO PDF that can be viewed from the Notifications panel.

All monetary values in the underlying PO are stored in USD. For vendor-facing
PDFs we render amounts in Indian rupees (INR) using currency_utils.
"""

from datetime import datetime
from typing import Dict, Any
import io
import os

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

from currency_utils import usd_to_inr


def _get_logo_path() -> str | None:
    """
    Try to find the HeartKart logo in common locations.
    Returns absolute path or None if not found.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    possible_paths = [
        os.path.join(script_dir, '..', '..', 'inventory-dashboard', 'public', 'heartkart_logo.png'),
        os.path.join(script_dir, '..', 'inventory-dashboard', 'public', 'heartkart_logo.png'),
        os.path.join(script_dir, 'inventory-dashboard', 'public', 'heartkart_logo.png'),
        'inventory-dashboard/public/heartkart_logo.png',
    ]
    for path in possible_paths:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            return abs_path
    return None


def generate_vendor_po_pdf(po: Dict[str, Any]) -> bytes:
    """
    Generate a PDF for a single-vendor PO.
    
    Args:
        po: PO dictionary from vendor_orchestrator_v2.generate_purchase_order
    Returns:
        PDF bytes
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Margins
    margin = 0.75 * inch
    x = margin
    y = height - margin

    # Header with logo + title bar
    logo_path = _get_logo_path()
    title_x = x
    if logo_path:
        try:
            img = ImageReader(logo_path)
            img_width, img_height = img.getSize()
            # Scale logo to reasonable width
            desired_width = 1.8 * inch
            scale = desired_width / float(img_width or 1)
            logo_width = desired_width
            logo_height = img_height * scale
            c.drawImage(
                img,
                x,
                y - logo_height,
                width=logo_width,
                height=logo_height,
                mask='auto'
            )
            title_x = x + logo_width + 0.4 * inch
            y -= max(logo_height, 0.9 * inch)
        except Exception:
            # Fallback to text-only header
            pass

    # Title
    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(colors.HexColor("#111827"))
    c.drawString(title_x, y, "Purchase Order")
    y -= 0.3 * inch

    # PO meta
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.black)
    c.drawString(x, y, f"PO Number: {po.get('po_number', '')}")
    y -= 0.18 * inch
    c.drawString(x, y, f"Date: {po.get('date', '')[:10]}")
    y -= 0.35 * inch

    # Vendor / Buyer info
    vendor = po.get("vendor", {}) or {}
    buyer = po.get("buyer", {}) or {}

    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, "Vendor")
    c.drawString(width / 2, y, "Buyer")
    y -= 0.18 * inch

    c.setFont("Helvetica", 10)
    c.drawString(x, y, vendor.get("name", ""))
    c.drawString(width / 2, y, buyer.get("company", ""))
    y -= 0.18 * inch

    c.drawString(x, y, vendor.get("phone", ""))
    c.drawString(width / 2, y, buyer.get("contact", ""))
    y -= 0.18 * inch

    c.drawString(x, y, vendor.get("email", ""))
    c.drawString(width / 2, y, buyer.get("email", ""))
    y -= 0.3 * inch

    # Order meta
    c.setFont("Helvetica", 10)
    c.drawString(x, y, f"Delivery Date: {po.get('delivery_date', 'as soon as possible')}")
    y -= 0.18 * inch
    c.drawString(x, y, f"Payment Terms: {po.get('payment_terms', 'Net 30')}")
    y -= 0.3 * inch

    # Items header with light gray bar
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x, y, "Items")
    y -= 0.22 * inch

    header_height = 0.22 * inch
    table_width = width - 2 * margin
    c.setFillColor(colors.HexColor("#F3F4F6"))
    c.rect(x, y - header_height + 2, table_width, header_height, fill=1, stroke=0)

    c.setFillColor(colors.HexColor("#111827"))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + 4, y - header_height / 2 + 2, "Description")
    c.drawRightString(x + 3.7 * inch, y - header_height / 2 + 2, "Qty")
    c.drawRightString(x + 5.0 * inch, y - header_height / 2 + 2, "Unit Price")
    c.drawRightString(x + 6.5 * inch, y - header_height / 2 + 2, "Total")
    y -= header_height + 0.04 * inch

    c.setFont("Helvetica", 9)
    items = po.get("items", []) or []
    for item in items:
        if y < margin + 1.2 * inch:
            c.showPage()
            y = height - margin
            c.setFont("Helvetica-Bold", 11)
            c.drawString(x, y, "Items (cont.)")
            y -= 0.22 * inch
            c.setFont("Helvetica", 9)

        name = item.get("name", "")
        qty = item.get("quantity", 0)
        unit_price_usd = item.get("unit_price", 0.0)
        total_usd = item.get("total", qty * unit_price_usd)

        unit_price_inr = usd_to_inr(unit_price_usd)
        total_inr = usd_to_inr(total_usd)

        c.drawString(x, y, name[:40])
        c.drawRightString(x + 3.7 * inch, y, str(qty))
        c.drawRightString(x + 5.0 * inch, y, f"₹{unit_price_inr:,.2f}")
        c.drawRightString(x + 6.5 * inch, y, f"₹{total_inr:,.2f}")
        y -= 0.16 * inch

    # Totals block with subtle divider
    y -= 0.12 * inch
    c.setStrokeColor(colors.HexColor("#E5E7EB"))
    c.setLineWidth(0.5)
    c.line(x, y, x + table_width, y)
    y -= 0.18 * inch

    # Totals are calculated in USD in the PO; convert to INR for display
    subtotal_usd = po.get("subtotal", 0)
    tax_usd = po.get("tax", 0)
    total_usd = po.get("total_amount", 0)

    subtotal_inr = usd_to_inr(subtotal_usd)
    tax_inr = usd_to_inr(tax_usd)
    total_inr = usd_to_inr(total_usd)

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#111827"))
    c.drawRightString(x + 5.0 * inch, y, "Subtotal:")
    c.setFont("Helvetica", 10)
    c.drawRightString(x + 6.5 * inch, y, f"₹{subtotal_inr:,.2f}")
    y -= 0.18 * inch

    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(x + 5.0 * inch, y, "Tax:")
    c.setFont("Helvetica", 10)
    c.drawRightString(x + 6.5 * inch, y, f"₹{tax_inr:,.2f}")
    y -= 0.18 * inch

    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(x + 5.0 * inch, y, "TOTAL:")
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(x + 6.5 * inch, y, f"₹{total_inr:,.2f}")
    y -= 0.35 * inch

    # Footer note
    c.setFont("Helvetica", 8)
    c.drawString(
        x,
        margin,
        f"Generated by HeartKart on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    )

    c.showPage()
    c.save()

    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


