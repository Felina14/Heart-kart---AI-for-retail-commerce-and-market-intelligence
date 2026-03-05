#!/usr/bin/env python3
"""
Beautiful Vendor-Ready Purchase Order Generator for HeartKart
Clean, modern design with proper branding
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
# Import ImageReader - Pillow is now available in Lambda via manylinux wheels
try:
    from reportlab.lib.utils import ImageReader
    HAS_IMAGE_READER = True
except ImportError:
    HAS_IMAGE_READER = False
    ImageReader = None
from datetime import datetime, timedelta
import io
import os
from typing import List, Dict

# HeartKart Brand Colors
BRAND_RED = '#E11D48'
BRAND_LIGHT_RED = '#FEE2E2'
BRAND_DARK_GRAY = '#374151'
BRAND_GRAY = '#6B7280'
BRAND_LIGHT_GRAY = '#F9FAFB'

# Company Information
COMPANY_INFO = {
    'name': 'HeartKart',
    'address': '123 Valentine Avenue',
    'city': 'New York, NY 10025',
    'phone': '+1 (555) HEART-25',
    'email': 'orders@heartkart.com',
    'buyer': 'Sarah Chen',
    'buyer_title': 'Procurement Manager'
}


def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple (0-1 range)"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))


def truncate_text(text: str, max_width: float, font_name: str = 'Helvetica', font_size: int = 10) -> str:
    """Truncate text with ellipsis so it fits within max_width (points)."""
    if pdfmetrics.stringWidth(text, font_name, font_size) <= max_width:
        return text

    ellipsis = '…'
    ellipsis_width = pdfmetrics.stringWidth(ellipsis, font_name, font_size)
    max_text_width = max_width - ellipsis_width
    if max_text_width <= 0:
        return ellipsis

    # Walk backwards until it fits
    for i in range(len(text), 0, -1):
        candidate = text[:i]
        if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_text_width:
            return candidate + ellipsis

    return ellipsis


def get_logo_path():
    """Get the path to the HeartKart logo image"""
    # In Lambda, logo won't be available, so we'll use text fallback
    # Try multiple possible paths for local development
    script_dir = os.path.dirname(os.path.abspath(__file__))
    possible_paths = [
        os.path.join(script_dir, '..', '..', 'inventory-dashboard', 'public', 'heartkart_logo.png'),
        os.path.join(script_dir, '..', 'inventory-dashboard', 'public', 'heartkart_logo.png'),
        '/var/task/inventory-dashboard/public/heartkart_logo.png',  # Lambda path
        'inventory-dashboard/public/heartkart_logo.png',
        '../inventory-dashboard/public/heartkart_logo.png',
    ]
    
    for path in possible_paths:
        abs_path = os.path.abspath(path) if not path.startswith('/var/task') else path
        if os.path.exists(abs_path):
            return abs_path
    
    return None


def draw_logo(c, x, y, max_width=4*inch):
    """Draw HeartKart logo from image file, returns logo height.
    
    max_width is in points (ReportLab units), so pass values like 3*inch.
    """
    c.saveState()
    logo_path = get_logo_path()
    logo_height = 0.8 * inch  # Default height
    
    if logo_path and os.path.exists(logo_path) and HAS_IMAGE_READER:
        try:
            # Load and draw the logo image
            img = ImageReader(logo_path)
            img_width, img_height = img.getSize()

            # Calculate aspect ratio and scale to fit max_width (all in points)
            aspect_ratio = img_height / float(img_width or 1)
            logo_width = min(max_width, img_width)  # both are in points
            logo_height = logo_width * aspect_ratio

            # Draw the logo
            c.drawImage(
                img,
                x,
                y - logo_height,
                width=logo_width,
                height=logo_height,
                preserveAspectRatio=True,
                mask='auto',
            )
        except Exception as e:
            # Fallback to text
            c.setFont('Helvetica-Bold', 24)
            rgb = hex_to_rgb(BRAND_RED)
            c.setFillColorRGB(*rgb)
            c.drawString(x, y - 20, 'HeartKart')
            logo_height = 0.3 * inch
    else:
        # Fallback to text if logo not found
        c.setFont('Helvetica-Bold', 24)
        rgb = hex_to_rgb(BRAND_RED)
        c.setFillColorRGB(*rgb)
        c.drawString(x, y - 20, 'HeartKart')
        logo_height = 0.3 * inch
    
    c.restoreState()
    return logo_height


def create_vendor_po_pdf(vendor_name: str, po_data: Dict, vendor_items: List[Dict], output_path: str = None) -> bytes:
    """
    Generate a beautiful, vendor-ready PO
    """
    buffer = io.BytesIO() if not output_path else None
    c = canvas.Canvas(output_path or buffer, pagesize=letter)
    width, height = letter
    
    # Margins - bring content slightly higher on page
    margin_left = 0.50 * inch
    margin_right = width - 0.50 * inch
    margin_top = height - 0.25 * inch
    margin_bottom = 0.25 * inch
    
    y = margin_top
    
    # ===== HEADER SECTION =====
    # Logo with proper spacing
    logo_height = draw_logo(c, margin_left, y, max_width=3*inch)
    y -= logo_height + 0.25 * inch  # Space for logo plus padding
    
    # PO Title and Number - better alignment
    c.setFont('Helvetica-Bold', 22)
    c.setFillColorRGB(*hex_to_rgb(BRAND_DARK_GRAY))
    c.drawString(margin_left, y, 'PURCHASE ORDER')
    y -= 40
    
    # PO Details - better formatting
    po_date = datetime.fromisoformat(po_data['date']).strftime('%B %d, %Y')
    
    # PO Number on left
    c.setFont('Helvetica', 11)
    c.setFillColorRGB(*hex_to_rgb(BRAND_GRAY))
    po_num_label = 'PO Number:'
    po_num_label_width = c.stringWidth(po_num_label, 'Helvetica', 11)
    c.drawString(margin_left, y, po_num_label)
    c.setFont('Helvetica-Bold', 11)
    c.setFillColorRGB(*hex_to_rgb(BRAND_DARK_GRAY))
    c.drawString(margin_left + po_num_label_width + 6, y, po_data['po_number'])
    
    # Date on right (label + value, left-aligned as a block to avoid overlap)
    date_label = 'Date:'
    c.setFont('Helvetica-Bold', 11)
    date_value_width = c.stringWidth(po_date, 'Helvetica-Bold', 11)
    date_label_width = c.stringWidth(date_label + ' ', 'Helvetica-Bold', 11)
    total_date_width = date_label_width + date_value_width

    date_block_x = margin_right - total_date_width
    c.setFillColorRGB(*hex_to_rgb(BRAND_GRAY))
    c.drawString(date_block_x, y, date_label)
    c.setFillColorRGB(*hex_to_rgb(BRAND_DARK_GRAY))
    c.drawString(date_block_x + date_label_width, y, po_date)
    
    y -= 40
    
    # ===== VENDOR/SHIPPING INFO BOXES =====
    box_spacing = 12
    box_width = (margin_right - margin_left - 2 * box_spacing) / 3
    box_height = 120  # Taller for better spacing
    box_y = y - box_height
    
    # Draw three boxes with proper spacing
    boxes = [
        ('VENDOR', margin_left),
        ('SHIP TO', margin_left + box_width + box_spacing),
        ('BILL TO', margin_left + 2 * (box_width + box_spacing))
    ]
    
    for title, box_x in boxes:
        # Box background
        c.setFillColorRGB(*hex_to_rgb(BRAND_LIGHT_GRAY))
        c.rect(box_x, box_y, box_width, box_height, fill=True, stroke=False)
        
        # Box border
        c.setStrokeColorRGB(*hex_to_rgb('#E5E7EB'))
        c.setLineWidth(1)
        c.rect(box_x, box_y, box_width, box_height, fill=False, stroke=True)
        
        # Title bar
        c.setFillColorRGB(*hex_to_rgb(BRAND_RED))
        c.rect(box_x, box_y + box_height - 25, box_width, 25, fill=True, stroke=False)
        
        # Title text
        c.setFont('Helvetica-Bold', 10)
        c.setFillColor(colors.white)
        c.drawString(box_x + 10, box_y + box_height - 17, title)
    
    # Fill in content
    c.setFont('Helvetica', 9)
    c.setFillColorRGB(*hex_to_rgb(BRAND_DARK_GRAY))
    
    # Vendor box
    vendor_lead_time = vendor_items[0]['lead_time_days']
    need_by_date = (datetime.now() + timedelta(days=vendor_lead_time + 3)).strftime('%B %d, %Y')
    
    text_y = box_y + box_height - 40
    c.drawString(boxes[0][1] + 10, text_y, vendor_name)
    text_y -= 15
    c.setFont('Helvetica-Bold', 8)
    c.drawString(boxes[0][1] + 10, text_y, 'Need By:')
    c.setFont('Helvetica', 8)
    c.drawString(boxes[0][1] + 50, text_y, need_by_date)
    text_y -= 12
    c.setFont('Helvetica-Bold', 8)
    c.drawString(boxes[0][1] + 10, text_y, 'Lead Time:')
    c.setFont('Helvetica', 8)
    c.drawString(boxes[0][1] + 50, text_y, f"{vendor_lead_time} days")
    
    # Ship To box
    text_y = box_y + box_height - 40
    c.setFont('Helvetica-Bold', 9)
    c.drawString(boxes[1][1] + 10, text_y, COMPANY_INFO['name'])
    text_y -= 14
    c.setFont('Helvetica', 8)
    c.drawString(boxes[1][1] + 10, text_y, COMPANY_INFO['address'])
    text_y -= 12
    c.drawString(boxes[1][1] + 10, text_y, COMPANY_INFO['city'])
    
    # Bill To box
    text_y = box_y + box_height - 40
    c.setFont('Helvetica-Bold', 9)
    c.drawString(boxes[2][1] + 10, text_y, COMPANY_INFO['name'])
    text_y -= 14
    c.setFont('Helvetica', 8)
    c.drawString(boxes[2][1] + 10, text_y, 'Accounts Payable')
    text_y -= 12
    c.drawString(boxes[2][1] + 10, text_y, COMPANY_INFO['address'])
    text_y -= 12
    c.drawString(boxes[2][1] + 10, text_y, COMPANY_INFO['city'])
    
    y = box_y - 30
    
    # ===== LINE ITEMS TABLE =====
    # Table header
    table_y = y
    header_height = 35  # Taller header

    # Header background
    c.setFillColorRGB(*hex_to_rgb(BRAND_RED))
    c.rect(margin_left, table_y - header_height, margin_right - margin_left, header_height, fill=True, stroke=False)

    # Column widths (points) tuned to avoid overlap
    table_width = margin_right - margin_left
    sku_col_width = 80
    desc_col_width = 150
    qty_col_width = 40
    unit_col_width = 60
    total_col_width = table_width - (sku_col_width + desc_col_width + qty_col_width + unit_col_width)

    # X positions for columns
    sku_x = margin_left + 10
    desc_x = sku_x + sku_col_width + 6
    qty_center_x = desc_x + desc_col_width + qty_col_width / 2
    unit_right_x = qty_center_x + qty_col_width / 2 + unit_col_width
    total_right_x = unit_right_x + total_col_width - 6

    # Header text
    c.setFont('Helvetica-Bold', 11)
    c.setFillColor(colors.white)
    header_baseline = table_y - 22

    c.drawString(sku_x, header_baseline, 'SKU')
    c.drawString(desc_x, header_baseline, 'Description')
    c.drawCentredString(qty_center_x, header_baseline, 'Qty')
    c.drawRightString(unit_right_x, header_baseline, 'Unit Price')
    c.drawRightString(total_right_x, header_baseline, 'Line Total')
    
    table_y -= header_height
    
    # Table rows
    row_height = 42  # Slightly shorter rows to keep footer visible
    subtotal = 0
    alternate = True
    
    for item in vendor_items:
        # Calculate correct amounts
        unit_price = round(item['estimated_cost'] / item['recommended_order_qty'], 2)
        line_total = round(unit_price * item['recommended_order_qty'], 2)
        subtotal += line_total
        
        # Row background
        if alternate:
            c.setFillColorRGB(*hex_to_rgb(BRAND_LIGHT_GRAY))
            c.rect(margin_left, table_y - row_height, margin_right - margin_left, row_height, fill=True, stroke=False)
        alternate = not alternate
        
        # Row border
        c.setStrokeColorRGB(*hex_to_rgb('#E5E7EB'))
        c.setLineWidth(0.5)
        c.line(margin_left, table_y, margin_right, table_y)
        
        # Row text - better vertical alignment
        c.setFont('Helvetica', 10)
        c.setFillColorRGB(*hex_to_rgb(BRAND_DARK_GRAY))

        # SKU (truncate if extremely long)
        sku_text = truncate_text(item['sku'], sku_col_width - 10, 'Helvetica', 10)
        c.drawString(sku_x, table_y - 20, sku_text)

        # Description (name + category) with safe width
        desc_max_width = desc_col_width - 12
        name_text = truncate_text(item['name'], desc_max_width, 'Helvetica-Bold', 10)
        category_text = f"({item['category']})"
        category_text = truncate_text(category_text, desc_max_width, 'Helvetica', 9)

        c.setFont('Helvetica-Bold', 10)
        c.drawString(desc_x, table_y - 18, name_text)
        c.setFont('Helvetica', 9)
        c.setFillColorRGB(*hex_to_rgb(BRAND_GRAY))
        c.drawString(desc_x, table_y - 32, category_text)

        # Quantity
        c.setFont('Helvetica', 10)
        c.setFillColorRGB(*hex_to_rgb(BRAND_DARK_GRAY))
        c.drawCentredString(qty_center_x, table_y - 20, str(item['recommended_order_qty']))

        # Unit Price
        c.drawRightString(unit_right_x, table_y - 20, f"${unit_price:,.2f}")

        # Line Total
        c.setFont('Helvetica-Bold', 11)
        c.drawRightString(total_right_x, table_y - 20, f"${line_total:,.2f}")
        
        table_y -= row_height
    
    # Bottom border
    c.setStrokeColorRGB(*hex_to_rgb('#E5E7EB'))
    c.setLineWidth(1)
    c.line(margin_left, table_y, margin_right, table_y)
    
    table_y -= 30
    
    # ===== TOTALS SECTION =====
    totals_x = margin_right - 240  # Wider totals section for better alignment
    
    c.setFont('Helvetica', 11)
    c.setFillColorRGB(*hex_to_rgb(BRAND_GRAY))
    
    # Subtotal
    c.drawString(totals_x, table_y, 'Subtotal:')
    c.setFont('Helvetica-Bold', 11)
    c.setFillColorRGB(*hex_to_rgb(BRAND_DARK_GRAY))
    c.drawRightString(margin_right - 12, table_y, f"${subtotal:,.2f}")
    table_y -= 20
    
    # Shipping
    c.setFont('Helvetica', 11)
    c.setFillColorRGB(*hex_to_rgb(BRAND_GRAY))
    c.drawString(totals_x, table_y, 'Shipping:')
    c.setFont('Helvetica', 11)
    c.drawRightString(margin_right - 12, table_y, 'TBD')
    table_y -= 20
    
    # Tax
    c.drawString(totals_x, table_y, 'Tax:')
    c.drawRightString(margin_right - 12, table_y, 'Tax Exempt')
    table_y -= 30
    
    # Total line - thicker and more prominent
    c.setStrokeColorRGB(*hex_to_rgb(BRAND_RED))
    c.setLineWidth(3)
    c.line(totals_x, table_y + 5, margin_right - 12, table_y + 5)
    table_y -= 15
    
    # Grand Total - larger and bolder
    c.setFont('Helvetica-Bold', 18)
    c.setFillColorRGB(*hex_to_rgb(BRAND_RED))
    c.drawString(totals_x, table_y, 'TOTAL:')
    c.drawRightString(margin_right - 12, table_y, f"${subtotal:,.2f}")
    
    table_y -= 40
    
    # ===== TERMS & NOTES =====
    # Payment Terms and Incoterms on same line
    c.setFont('Helvetica-Bold', 10)
    c.setFillColorRGB(*hex_to_rgb(BRAND_DARK_GRAY))
    terms_label_width = c.stringWidth('PAYMENT TERMS:', 'Helvetica-Bold', 10)
    c.drawString(margin_left, table_y, 'PAYMENT TERMS:')
    c.setFont('Helvetica', 10)
    c.drawString(margin_left + terms_label_width + 8, table_y, 'Net 30')
    
    # Incoterms
    incoterms_x = margin_left + 200
    c.setFont('Helvetica-Bold', 10)
    c.setFillColorRGB(*hex_to_rgb(BRAND_DARK_GRAY))
    incoterms_label_width = c.stringWidth('INCOTERMS:', 'Helvetica-Bold', 10)
    c.drawString(incoterms_x, table_y, 'INCOTERMS:')
    c.setFont('Helvetica', 10)
    c.drawString(incoterms_x + incoterms_label_width + 8, table_y, 'DDP (Delivered Duty Paid)')
    
    table_y -= 30
    
    # Notes section
    c.setFont('Helvetica-Bold', 10)
    c.setFillColorRGB(*hex_to_rgb(BRAND_DARK_GRAY))
    c.drawString(margin_left, table_y, 'NOTES:')
    table_y -= 20
    
    c.setFont('Helvetica', 10)
    c.setFillColorRGB(*hex_to_rgb(BRAND_GRAY))
    notes = [
        '• Please confirm receipt and estimated delivery date within 24 hours',
        '• All items must meet quality standards as per our vendor agreement',
        '• Include PO number on all shipping documents and invoices'
    ]
    
    for note in notes:
        c.drawString(margin_left + 12, table_y, note)
        table_y -= 18
    
    table_y -= 20
    
    # ===== BUYER CONTACT =====
    c.setFont('Helvetica-Bold', 10)
    c.setFillColorRGB(*hex_to_rgb(BRAND_DARK_GRAY))
    c.drawString(margin_left, table_y, 'BUYER CONTACT:')
    table_y -= 20
    
    c.setFont('Helvetica', 10)
    c.setFillColorRGB(*hex_to_rgb(BRAND_GRAY))
    c.drawString(margin_left + 12, table_y, f"{COMPANY_INFO['buyer']}, {COMPANY_INFO['buyer_title']}")
    table_y -= 16
    c.drawString(margin_left + 12, table_y, f"Email: {COMPANY_INFO['email']}")
    table_y -= 16
    c.drawString(margin_left + 12, table_y, f"Phone: {COMPANY_INFO['phone']}")
    
    # ===== FOOTER =====
    c.setFont('Helvetica', 9)
    c.setFillColorRGB(*hex_to_rgb(BRAND_DARK_GRAY))
    # Place footer slightly above bottom edge so it's always visible
    c.drawRightString(margin_right, 0.5 * inch, 'Page 1 of 1')
    
    # Save
    c.showPage()
    c.save()
    
    if buffer:
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes
    
    return None


def create_po_pdf(po_data: Dict, output_path: str = None) -> bytes:
    """Generate vendor-ready PO PDF"""
    # Validate input
    if not po_data or 'items' not in po_data:
        raise ValueError("PO data must contain 'items' list")
    
    if not po_data['items']:
        raise ValueError("PO data must have at least one item")
    
    # Group items by vendor
    items_by_vendor = {}
    for item in po_data['items']:
        if 'vendor' not in item:
            raise ValueError(f"Item {item.get('sku', 'unknown')} missing 'vendor' field")
        vendor = item['vendor']
        if vendor not in items_by_vendor:
            items_by_vendor[vendor] = []
        items_by_vendor[vendor].append(item)
    
    if not items_by_vendor:
        raise ValueError("No valid items with vendors found")
    
    # For now, create PO for first vendor
    # TODO: Handle multiple vendors
    first_vendor = list(items_by_vendor.keys())[0]
    return create_vendor_po_pdf(first_vendor, po_data, items_by_vendor[first_vendor], output_path)


if __name__ == '__main__':
    # Test
    sample_po = {
        'po_number': 'PO-20251116-143022',
        'date': datetime.now().isoformat(),
        'total_items': 3,
        'total_cost': 11499.25,
        'items': [
            {
                'sku': 'TREE-ARTIFICIAL-7FT',
                'name': 'Premium Valentine Gift Basket',
                'category': 'trees',
                'recommended_order_qty': 25,
                'vendor': 'Evergreen Suppliers',
                'lead_time_days': 10,
                'estimated_cost': 3999.75,
            },
            {
                'sku': 'WREATH-DECORATED-30',
                'name': 'Decorated Holiday Wreath (30 inch)',
                'category': 'decorations',
                'recommended_order_qty': 50,
                'vendor': 'Evergreen Suppliers',
                'lead_time_days': 10,
                'estimated_cost': 3499.50,
            },
            {
                'sku': 'INFLATABLE-SANTA-6FT',
                'name': 'Santa Claus Inflatable 6ft',
                'category': 'decorations',
                'recommended_order_qty': 50,
                'vendor': 'Evergreen Suppliers',
                'lead_time_days': 10,
                'estimated_cost': 4000.00,
            }
        ]
    }
    
    print("🎄 Generating beautiful vendor-ready PO...")
    create_po_pdf(sample_po, 'beautiful_po.pdf')
    print("✅ PDF generated: beautiful_po.pdf")
