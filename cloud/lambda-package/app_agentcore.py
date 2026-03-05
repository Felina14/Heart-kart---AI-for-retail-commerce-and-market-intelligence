#!/usr/bin/env python3
"""
HeartKart Inventory Management API — Cloud / AgentCore Edition
==============================================================
This backend routes ALL frontend API calls to the deployed AgentCore
agents (on Bedrock) and the Vendor Caller (on EC2), instead of running
agent logic locally.

Usage:
    python app_agentcore.py          # Runs on http://localhost:5000

Architecture:
    Frontend ──► app_agentcore.py ──► AgentCore agents (8 agents on Bedrock)
                                  ──► Vendor Caller EC2 (WebSocket + REST)
                                  ──► DynamoDB (inventory data, direct)
"""

from flask import Flask, jsonify, request, send_file, Response
from flask_cors import CORS
import boto3
import json
import os
import sys
import io
import time
import threading
import traceback
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# AWS Configuration — set profile BEFORE any boto3 usage
# ---------------------------------------------------------------------------
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# The AgentCore agents + DynamoDB are in the 'heartkart-deploy' AWS account.
# Setting AWS_PROFILE env var ensures ALL boto3 clients (including those in
# product_data_access.py) use the correct credentials automatically.
AWS_PROFILE = os.getenv("AWS_PROFILE_AGENTCORE", "heartkart-deploy")
os.environ.setdefault("AWS_PROFILE", AWS_PROFILE)

try:
    deploy_session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    _sts = deploy_session.client("sts")
    _acct = _sts.get_caller_identity()["Account"]
    print(f"📍 Using AWS profile: {AWS_PROFILE}  (account: {_acct})")
except Exception as _e:
    # In Lambda / cloud environments there's no named profile — clear the env var
    # so boto3 falls back to IAM role credentials.
    os.environ.pop("AWS_PROFILE", None)
    deploy_session = boto3.Session(region_name=AWS_REGION)
    print(f"📍 Using default AWS credentials (profile '{AWS_PROFILE}' not found: {_e})")

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)
CORS(app)

from botocore.config import Config as BotoConfig
agentcore_client = deploy_session.client(
    "bedrock-agentcore",
    region_name=AWS_REGION,
    config=BotoConfig(read_timeout=300, connect_timeout=10, retries={"max_attempts": 1}),
)

# ---------------------------------------------------------------------------
# Deployed AgentCore Agent ARNs  (account 583880312323)
# ---------------------------------------------------------------------------
AGENT_ARNS = {
    "replenishment_planner": "arn:aws:bedrock-agentcore:us-east-1:583880312323:runtime/heartkart_replenishment_planner-XOV1Fs7FQg",
    "stockout_sentinel":     "arn:aws:bedrock-agentcore:us-east-1:583880312323:runtime/heartkart_stockout_sentinel-SVao77AZkN",
    "inventory_copilot":     "arn:aws:bedrock-agentcore:us-east-1:583880312323:runtime/heartkart_inventory_copilot-AqG2gM81So",
    "exception_investigator":"arn:aws:bedrock-agentcore:us-east-1:583880312323:runtime/heartkart_exception_investigator-JnGYePH7Ih",
    "markdown_coach":        "arn:aws:bedrock-agentcore:us-east-1:583880312323:runtime/heartkart_markdown_coach-4VuN2TB1l4",
    "market_intelligence":   "arn:aws:bedrock-agentcore:us-east-1:583880312323:runtime/heartkart_market_intelligence-UV6jX76pJK",
    "pricing_intelligence":  "arn:aws:bedrock-agentcore:us-east-1:583880312323:runtime/heartkart_pricing_intelligence-BpoKvYFNfq",
    "email_drafter":         "arn:aws:bedrock-agentcore:us-east-1:583880312323:runtime/heartkart_email_drafter-l15N4AEAaF",
}

# ---------------------------------------------------------------------------
# Vendor Caller EC2 URL  (Caddy + aiohttp on EC2 with Elastic IP)
# ---------------------------------------------------------------------------
VENDOR_CALLER_URL = os.getenv(
    "VENDOR_CALLER_URL",
    "https://34-204-233-141.sslip.io"
)

# ---------------------------------------------------------------------------
# Twilio (for call-status lookups that query Twilio directly)
# ---------------------------------------------------------------------------
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")

# ---------------------------------------------------------------------------
# In-memory stores (same as original app.py for frontend compat)
# ---------------------------------------------------------------------------
orders_store = []          # Confirmed orders list
call_metadata_store = {}   # Call SID → metadata
call_transcripts_store = {}  # Call SID → transcript

# ---------------------------------------------------------------------------
# PO PDF generation + serving
# ---------------------------------------------------------------------------
# Use /tmp in Lambda (read-only filesystem), local dir otherwise
_base = "/tmp" if os.getenv("AWS_LAMBDA_FUNCTION_NAME") else os.path.dirname(os.path.abspath(__file__))
PO_PDF_DIR = os.path.join(_base, "generated_pos")
os.makedirs(PO_PDF_DIR, exist_ok=True)


def _extract_rejection_reason_cloud(transcript: str) -> str:
    """Extract the vendor's rejection reason from the call transcript."""
    if not transcript:
        return 'Vendor declined the order'

    transcript_lower = transcript.lower()
    reason_keywords = [
        ('out of stock', 'Out of stock'),
        ('no stock', 'No stock available'),
        ('not available', 'Product not available'),
        ('cannot fulfill', 'Cannot fulfill the order'),
        ("can't fulfill", 'Cannot fulfill the order'),
        ("don't have", 'Does not have the product'),
        ('do not have', 'Does not have the product'),
        ('sold out', 'Sold out'),
        ('back order', 'Product is on back order'),
        ('backorder', 'Product is on back order'),
        ('discontinued', 'Product discontinued'),
        ('too short', 'Delivery timeline too short'),
        ('not enough time', 'Not enough time to fulfill'),
        ('price too low', 'Price too low'),
        ('minimum order', 'Below minimum order quantity'),
        ('not interested', 'Vendor not interested'),
        ('capacity', 'Insufficient capacity'),
    ]

    for keyword, reason in reason_keywords:
        if keyword in transcript_lower:
            return reason

    # Fallback: try to extract vendor's last statement
    lines = transcript.strip().split('\n')
    vendor_lines = [l for l in lines if 'Vendor' in l]
    if vendor_lines:
        last_vendor_line = vendor_lines[-1]
        text = last_vendor_line.split(':', 1)[-1].strip() if ':' in last_vendor_line else last_vendor_line
        if 10 < len(text) < 200:
            return text

    return 'Vendor declined the order'


def _generate_po_pdf(po_number, vendor_name, contact_person, items,
                     total_amount, delivery_date, inr_rate=1.0):
    """Generate a PO PDF using fpdf2 (pure Python) and upload to S3. Returns URL or ''."""
    try:
        from fpdf import FPDF

        pdf = FPDF(orientation="P", unit="mm", format="letter")
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()

        W = pdf.w
        M = 15  # margin

        # Header bar
        pdf.set_fill_color(220, 20, 60)
        pdf.rect(0, 0, W, 22, style="F")
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 18)
        pdf.set_xy(M, 4)
        pdf.cell(0, 10, "HeartKart", new_x="LMARGIN")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_xy(W - 80, 4)
        pdf.cell(65, 5, "PURCHASE ORDER", align="R")
        pdf.set_xy(W - 80, 10)
        pdf.cell(65, 5, po_number, align="R")

        Y = 30

        # Date row
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_xy(M, Y)
        pdf.cell(90, 6, f"Date: {datetime.now().strftime('%B %d, %Y')}")
        pdf.set_xy(W - 80 - M, Y)
        pdf.cell(80, 6, f"Delivery: {delivery_date}", align="R")
        Y += 12

        # Vendor & Buyer
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(220, 20, 60)
        pdf.set_xy(M, Y)
        pdf.cell(80, 6, "VENDOR")
        pdf.set_xy(W / 2 + 5, Y)
        pdf.cell(80, 6, "BUYER")
        Y += 7
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(0, 0, 0)
        pdf.set_xy(M, Y)
        pdf.cell(80, 5, vendor_name)
        pdf.set_xy(W / 2 + 5, Y)
        pdf.cell(80, 5, "HeartKart Pvt. Ltd.")
        Y += 5
        pdf.set_xy(M, Y)
        pdf.cell(80, 5, f"Attn: {contact_person}")
        pdf.set_xy(W / 2 + 5, Y)
        pdf.cell(80, 5, "Attn: Priya Sharma")
        Y += 5
        pdf.set_xy(W / 2 + 5, Y)
        pdf.cell(80, 5, "procurement@heartkart.com")
        Y += 10

        # Table header
        col_w = [10, 70, 25, 35, 40]  # #, Desc, Qty, UnitPrice, Total
        table_w = sum(col_w)
        pdf.set_fill_color(254, 226, 226)
        pdf.set_text_color(153, 27, 27)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_xy(M, Y)
        pdf.cell(col_w[0], 7, "#", fill=True, align="C")
        pdf.cell(col_w[1], 7, "Description", fill=True)
        pdf.cell(col_w[2], 7, "Qty", fill=True, align="R")
        pdf.cell(col_w[3], 7, "Unit Price", fill=True, align="R")
        pdf.cell(col_w[4], 7, "Total", fill=True, align="R")
        Y += 8

        # Items
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(0, 0, 0)
        grand = 0.0
        for idx, item in enumerate(items, 1):
            name = item.get("name", "Item")[:45]
            qty = item.get("quantity", 0)
            up_inr = round(float(item.get("unit_price", 0)), 2)
            line_total = round(up_inr * qty, 2)
            grand += line_total

            if idx % 2 == 0:
                pdf.set_fill_color(255, 245, 245)
                fill = True
            else:
                fill = False

            pdf.set_xy(M, Y)
            pdf.cell(col_w[0], 6, str(idx), fill=fill, align="C")
            pdf.cell(col_w[1], 6, name, fill=fill)
            pdf.cell(col_w[2], 6, str(qty), fill=fill, align="R")
            pdf.cell(col_w[3], 6, f"Rs.{up_inr:,.2f}", fill=fill, align="R")
            pdf.cell(col_w[4], 6, f"Rs.{line_total:,.2f}", fill=fill, align="R")
            Y += 6

        if not items:
            grand = round(float(total_amount), 2)

        # Divider
        Y += 3
        pdf.set_draw_color(229, 231, 235)
        pdf.line(M, Y, M + table_w, Y)
        Y += 5

        # Grand total
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_xy(M, Y)
        pdf.cell(col_w[0] + col_w[1] + col_w[2] + col_w[3], 7, "GRAND TOTAL:", align="R")
        pdf.set_text_color(220, 20, 60)
        pdf.cell(col_w[4], 7, f"Rs.{grand:,.2f}", align="R")
        Y += 12

        # Payment terms
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_xy(M, Y)
        pdf.cell(0, 5, "Payment Terms: Net 30  |  Shipping: As per vendor terms")

        # Footer
        pdf.set_y(-20)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(156, 163, 175)
        pdf.cell(0, 5, f"Generated by HeartKart on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", align="L")
        pdf.set_y(-15)
        pdf.cell(0, 5, "This is a system-generated document.", align="R")

        pdf_bytes = pdf.output()

        # Save locally
        pdf_path = os.path.join(PO_PDF_DIR, f"{po_number}.pdf")
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)

        # Upload to S3 for persistent storage
        try:
            s3 = boto3.client("s3", region_name="us-east-1")
            s3_key = f"po-pdfs/{po_number}.pdf"
            s3.put_object(
                Bucket="heartkart-frontend",
                Key=s3_key,
                Body=pdf_bytes,
                ContentType="application/pdf",
            )
            url = f"https://heartkart-frontend.s3.amazonaws.com/{s3_key}"
            print(f"   ✅ PO PDF uploaded to S3: {url}")
            return url
        except Exception as s3_err:
            print(f"   ⚠️  S3 upload failed: {s3_err}, falling back to local")
            api_url = os.getenv("API_URL", "http://localhost:5000")
            url = f"{api_url.rstrip('/')}/api/po-pdfs/{po_number}.pdf"
            return url

    except Exception as e:
        print(f"   ⚠️  PDF generation failed: {e}")
        traceback.print_exc()
        return ""


# ============================================================================
# ROUTE: Generate PO PDF on demand
# ============================================================================

@app.route("/api/generate-po-pdf", methods=["POST"])
def generate_po_pdf_api():
    """Generate (or regenerate) a PO PDF from notification metadata."""
    try:
        data = request.json or {}
        po_number = data.get("po_number", "")
        vendor_name = data.get("vendor_name", "Vendor")
        meta = data.get("metadata", {})
        contact_person = meta.get("contact_person", "there")
        items = meta.get("items", [])
        total_amount = meta.get("total_amount", 0)
        delivery_date = meta.get("delivery_date", "as soon as possible")

        if not po_number:
            return jsonify({"error": "po_number is required"}), 400

        pdf_url = _generate_po_pdf(po_number, vendor_name, contact_person,
                                    items, total_amount, delivery_date, inr_rate=1.0)
        if pdf_url:
            return jsonify({"success": True, "pdf_url": pdf_url})
        else:
            return jsonify({"success": False, "error": "PDF generation failed"}), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# ROUTE: Serve generated PO PDFs
# ============================================================================

@app.route("/api/po-pdfs/<po_number>.pdf", methods=["GET"])
def serve_po_pdf(po_number):
    """Serve a generated PO PDF file — local first, then S3 fallback."""
    pdf_path = os.path.join(PO_PDF_DIR, f"{po_number}.pdf")
    if os.path.exists(pdf_path):
        return send_file(pdf_path, mimetype="application/pdf", download_name=f"{po_number}.pdf")

    # Fallback: fetch from S3
    try:
        s3 = boto3.client("s3", region_name="us-east-1")
        obj = s3.get_object(Bucket="heartkart-frontend", Key=f"po-pdfs/{po_number}.pdf")
        pdf_bytes = obj["Body"].read()
        # Cache locally
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        return send_file(pdf_path, mimetype="application/pdf", download_name=f"{po_number}.pdf")
    except Exception:
        return jsonify({"error": "PDF not found"}), 404


# ============================================================================
# HELPER: Invoke an AgentCore agent
# ============================================================================

def invoke_agent(agent_key: str, payload: dict, timeout: int = 120) -> dict:
    """
    Invoke a deployed AgentCore agent and return the parsed JSON response.
    """
    arn = AGENT_ARNS.get(agent_key)
    if not arn:
        raise ValueError(f"Unknown agent: {agent_key}")

    print(f"🤖 Invoking {agent_key} with payload: {json.dumps(payload, default=str)[:200]}")

    response = agentcore_client.invoke_agent_runtime(
        agentRuntimeArn=arn,
        qualifier="DEFAULT",
        payload=json.dumps(payload),
    )

    # Response body is a streaming blob
    body = response.get("response", response.get("body", b""))
    if hasattr(body, "read"):
        body = body.read()
    if isinstance(body, bytes):
        body = body.decode("utf-8")

    try:
        result = json.loads(body)
    except json.JSONDecodeError:
        result = {"raw_response": body}

    print(f"✅ {agent_key} responded (status={result.get('status', 'ok')})")
    return result


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "healthy",
        "mode": "agentcore_cloud",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "replenishment_planner": "agentcore",
            "stockout_sentinel": "agentcore",
            "inventory_copilot": "agentcore",
            "exception_investigator": "agentcore",
            "markdown_coach": "agentcore",
            "market_intelligence": "agentcore",
            "pricing_intelligence": "agentcore",
            "email_drafter": "agentcore",
            "vendor_caller": "ec2",
        },
        "vendor_caller_url": VENDOR_CALLER_URL,
    })


# ============================================================================
# INVENTORY (direct DynamoDB — no agent needed)
# ============================================================================

@app.route("/api/inventory", methods=["GET"])
def get_inventory():
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from product_data_access import get_inventory_for_frontend

        result = get_inventory_for_frontend(limit=10000)
        # get_inventory_for_frontend returns { success, count, inventory: [...] }
        # Frontend page.tsx reads data.inventory — keep as-is
        return jsonify(result)
    except Exception as e:
        print(f"Error fetching inventory: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# REPLENISHMENT PLANNER  →  AgentCore
# ============================================================================

@app.route("/api/replenishment/plan", methods=["GET"])
def get_replenishment_plan():
    try:
        threshold = int(request.args.get("threshold", 20))
        result = invoke_agent("replenishment_planner", {"action": "generate_plan", "threshold": threshold})
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/replenishment/urgent", methods=["GET"])
def get_urgent_reorders():
    try:
        result = invoke_agent("replenishment_planner", {"action": "generate_plan", "threshold": 20})
        urgent = [r for r in result.get("recommendations", []) if r.get("urgency") in ["CRITICAL", "HIGH"]]
        return jsonify({"status": "success", "count": len(urgent), "urgent_reorders": urgent})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/replenishment/by-vendor", methods=["GET"])
def get_reorders_by_vendor():
    try:
        result = invoke_agent("replenishment_planner", {"action": "generate_plan", "threshold": 20})
        by_vendor = {}
        for rec in result.get("recommendations", []):
            vendor = rec.get("vendor", "Unknown")
            if vendor not in by_vendor:
                by_vendor[vendor] = {"vendor_name": vendor, "total_items": 0, "total_cost": 0, "items": []}
            by_vendor[vendor]["total_items"] += 1
            by_vendor[vendor]["total_cost"] += rec.get("estimated_cost", 0)
            by_vendor[vendor]["items"].append(rec)
        return jsonify({"status": "success", "vendors": list(by_vendor.values())})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/replenishment/export-po", methods=["POST"])
def export_purchase_order():
    """Export PO as PDF — uses local PDF generation (lightweight utility)"""
    try:
        data = request.get_json()
        skus = data.get("skus", [])
        items = data.get("items", [])

        if items:
            selected = []
            for item in items:
                selected.append({
                    "sku": item.get("sku", f"SKU-{item.get('name', 'UNKNOWN').replace(' ', '-')}"),
                    "name": item.get("name", "Unknown Item"),
                    "category": item.get("category", "general"),
                    "recommended_order_qty": item.get("quantity", 1),
                    "vendor": item.get("vendor", "Unknown Vendor"),
                    "lead_time_days": item.get("lead_time_days", 7),
                    "estimated_cost": item.get("estimated_cost", item.get("quantity", 1) * item.get("unit_price", 0)),
                })
        elif skus:
            plan = invoke_agent("replenishment_planner", {"action": "generate_plan", "threshold": 20})
            selected = [r for r in plan.get("recommendations", []) if r.get("sku") in skus]
        else:
            return jsonify({"status": "error", "error": "No items or SKUs provided"}), 400

        if not selected:
            return jsonify({"status": "error", "error": "No items selected"}), 400

        po = {
            "po_number": f"PO-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            "date": datetime.now().isoformat(),
            "items": selected,
            "total_items": len(selected),
            "total_cost": sum(item.get("estimated_cost", 0) for item in selected),
        }

        # Try to use local PDF generator
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lambda-package", "agents", "replenishment_planner"))
            from pdf_generator_v2 import create_po_pdf

            pdf_bytes = create_po_pdf(po)
            return send_file(
                io.BytesIO(pdf_bytes),
                mimetype="application/pdf",
                as_attachment=True,
                download_name=f"{po['po_number']}.pdf",
            )
        except ImportError:
            # Fallback: return PO as JSON
            return jsonify({"status": "success", "po": po})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "error": str(e)}), 500


# ============================================================================
# STOCKOUT SENTINEL  →  AgentCore
# ============================================================================

@app.route("/api/stockout/report", methods=["GET"])
def get_stockout_report():
    try:
        risk_level = request.args.get("risk_level")
        category = request.args.get("category")
        result = invoke_agent("stockout_sentinel", {"action": "generate_report"})

        if result.get("status") != "success":
            return jsonify(result), 500

        products = result.get("at_risk_products", [])
        if risk_level:
            products = [p for p in products if p.get("risk_level") == risk_level.upper()]
        if category:
            products = [p for p in products if (p.get("category") or "").lower() == category.lower()]

        if risk_level or category:
            result["at_risk_products"] = products
            result["summary"]["total_at_risk"] = len(products)

        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/stockout/substitutes/<sku>", methods=["GET"])
def get_substitutes(sku):
    try:
        result = invoke_agent("stockout_sentinel", {"action": "get_substitute", "sku": sku})
        if result.get("status") == "error":
            return jsonify(result), 404
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/stockout/critical", methods=["GET"])
def get_critical_stockouts():
    try:
        result = invoke_agent("stockout_sentinel", {"action": "generate_report"})
        if result.get("status") != "success":
            return jsonify(result), 500
        critical = [p for p in result.get("at_risk_products", []) if p.get("risk_level") == "CRITICAL"]
        return jsonify({"status": "success", "count": len(critical), "critical_stockouts": critical})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/stockout/by-category", methods=["GET"])
def get_stockouts_by_category():
    try:
        result = invoke_agent("stockout_sentinel", {"action": "generate_report"})
        if result.get("status") != "success":
            return jsonify(result), 500

        by_category = {}
        for product in result.get("at_risk_products", []):
            cat = product.get("category", "Unknown")
            if cat not in by_category:
                by_category[cat] = {"category": cat, "total_products": 0, "critical_count": 0, "high_count": 0, "products": []}
            by_category[cat]["total_products"] += 1
            if product.get("risk_level") == "CRITICAL":
                by_category[cat]["critical_count"] += 1
            elif product.get("risk_level") == "HIGH":
                by_category[cat]["high_count"] += 1
            by_category[cat]["products"].append(product)

        return jsonify({"status": "success", "categories": list(by_category.values())})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/stockout/substitute-suggestions", methods=["POST"])
def get_bulk_substitutes():
    try:
        data = request.get_json()
        skus = data.get("skus", [])
        if not skus:
            return jsonify({"status": "error", "error": "No SKUs provided"}), 400

        results = []
        for sku in skus:
            try:
                r = invoke_agent("stockout_sentinel", {"action": "get_substitute", "sku": sku})
                if r.get("status") == "success":
                    results.append(r)
            except Exception:
                pass

        return jsonify({"status": "success", "count": len(results), "substitutes": results})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# ============================================================================
# INVENTORY COPILOT  →  AgentCore
# ============================================================================

@app.route("/api/copilot/query", methods=["POST"])
def copilot_query():
    try:
        data = request.get_json()
        query = data.get("query", "")
        if not query:
            return jsonify({"status": "error", "error": "No query provided"}), 400
        result = invoke_agent("inventory_copilot", {"query": query})
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/copilot/suggestions", methods=["GET"])
def copilot_suggestions():
    """Return static suggestions (no agent call needed)"""
    return jsonify({
        "status": "success",
        "suggestions": [
            "Show me all products with stock below 20",
            "What are the top 10 most expensive items?",
            "List all products in the Wreaths category",
            "Which products have the highest sales velocity?",
            "Show me products from vendor Sunrise Imports",
            "What items need reordering urgently?",
            "Compare prices across all candle products",
            "Which categories have the most products?",
        ],
    })


# ============================================================================
# EXCEPTION INVESTIGATOR  →  AgentCore
# ============================================================================

@app.route("/api/exceptions/investigate", methods=["GET"])
def investigate_exceptions_endpoint():
    try:
        days = int(request.args.get("days", 30))
        threshold = float(request.args.get("threshold", 2.0))
        result = invoke_agent("exception_investigator", {"days": days, "threshold": threshold})
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/exceptions/summary", methods=["GET"])
def exceptions_summary():
    try:
        days = int(request.args.get("days", 30))
        threshold = float(request.args.get("threshold", 2.0))
        result = invoke_agent("exception_investigator", {"days": days, "threshold": threshold})
        return jsonify({
            "status": result.get("status"),
            "summary": result.get("summary"),
            "insights": result.get("insights"),
            "generated_at": result.get("generated_at"),
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/exceptions/by-type/<anomaly_type>", methods=["GET"])
def exceptions_by_type(anomaly_type):
    try:
        days = int(request.args.get("days", 30))
        threshold = float(request.args.get("threshold", 2.0))
        result = invoke_agent("exception_investigator", {"days": days, "threshold": threshold})
        if result.get("status") != "success":
            return jsonify(result), 500
        filtered = [a for a in result.get("anomalies", []) if a.get("anomaly_type") == anomaly_type.upper()]
        return jsonify({"status": "success", "anomaly_type": anomaly_type.upper(), "count": len(filtered), "anomalies": filtered})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# ============================================================================
# MARKDOWN & CLEARANCE COACH  →  AgentCore
# ============================================================================

@app.route("/api/markdown/report", methods=["GET"])
def get_markdown_report():
    try:
        threshold = int(request.args.get("threshold", 60))
        result = invoke_agent("markdown_coach", {"age_threshold_days": threshold})
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/markdown/aged-inventory", methods=["GET"])
def get_aged_inventory():
    try:
        threshold = int(request.args.get("threshold", 60))
        result = invoke_agent("markdown_coach", {"age_threshold_days": threshold})
        aged = result.get("aged_products", result.get("recommendations", []))
        return jsonify({"status": "success", "threshold_days": threshold, "count": len(aged), "aged_products": aged})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/markdown/timeline", methods=["GET"])
def get_clearance_timeline():
    try:
        threshold = int(request.args.get("threshold", 60))
        result = invoke_agent("markdown_coach", {"age_threshold_days": threshold})
        timeline = result.get("timeline", result.get("clearance_timeline", []))
        return jsonify({"status": "success", "timeline": timeline})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/markdown/bundles", methods=["GET"])
def get_bundle_suggestions():
    try:
        threshold = int(request.args.get("threshold", 60))
        result = invoke_agent("markdown_coach", {"age_threshold_days": threshold})
        bundles = result.get("bundles", result.get("bundle_suggestions", []))
        return jsonify({"status": "success", "count": len(bundles), "bundles": bundles})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/markdown/summary", methods=["GET"])
def get_markdown_summary():
    try:
        threshold = int(request.args.get("threshold", 60))
        result = invoke_agent("markdown_coach", {"age_threshold_days": threshold})
        summary = result.get("summary", {})
        return jsonify({"status": "success", "summary": summary})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/markdown/apply", methods=["POST"])
def apply_markdown():
    """Apply a markdown to a product — updates price in DynamoDB."""
    try:
        data = request.json or {}
        sku = data.get("sku")
        new_price = data.get("new_price")

        if not sku or new_price is None:
            return jsonify({"status": "error", "error": "Missing sku or new_price"}), 400

        from decimal import Decimal

        products_table = deploy_session.resource("dynamodb", region_name=AWS_REGION).Table("valentines-products")
        products_table.update_item(
            Key={"sku": sku},
            UpdateExpression="SET price = :p",
            ExpressionAttributeValues={":p": Decimal(str(round(float(new_price), 2)))},
        )

        print(f"✅ Markdown applied: {sku} → ₹{new_price}")
        return jsonify({"status": "success", "sku": sku, "new_price": float(new_price)})
    except Exception as e:
        print(f"❌ Error applying markdown: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


# ============================================================================
# MARKET INTELLIGENCE  →  AgentCore
# ============================================================================

@app.route("/api/market-intelligence", methods=["GET", "POST"])
def get_market_intelligence():
    try:
        if request.method == "POST":
            data = request.json or {}
        else:
            data = request.args.to_dict()

        payload = {
            "query": data.get("query"),
            "category": data.get("category"),
            "region": data.get("region"),
            "report_type": data.get("report_type", "full"),
        }

        result = invoke_agent("market_intelligence", payload)

        return jsonify({
            "success": result.get("status") == "success" or "data" in result,
            "report_type": payload["report_type"],
            "data": result.get("data", result),
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# PRICING INTELLIGENCE  →  AgentCore
# ============================================================================

@app.route("/api/pricing-intelligence", methods=["GET", "POST"])
def get_pricing_intelligence():
    try:
        if request.method == "POST":
            data = request.json or {}
        else:
            data = request.args.to_dict()

        payload = {
            "query": data.get("query"),
            "sku": data.get("sku"),
            "category": data.get("category"),
            "analysis_type": data.get("analysis_type", "full"),
        }

        result = invoke_agent("pricing_intelligence", payload)

        return jsonify({
            "success": result.get("status") == "success",
            "analysis_type": payload["analysis_type"],
            "data": result,
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# EMAIL DRAFTER  →  AgentCore
# ============================================================================

@app.route("/api/draft-email", methods=["POST"])
def draft_email():
    try:
        data = request.json
        payload = {
            "vendor_name": data.get("vendor_name"),
            "contact_person": data.get("contact_person"),
            "po_number": data.get("po_number"),
            "items": data.get("items", []),
            "total_amount": data.get("total_amount", 0),
            "delivery_date": data.get("delivery_date"),
            "call_transcript": data.get("call_transcript"),
            "call_summary": data.get("call_summary"),
        }

        result = invoke_agent("email_drafter", payload)
        return jsonify({"success": True, "email": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# VENDOR CALLER  →  EC2 (proxy)
# ============================================================================

def _proxy_to_vendor_caller(method: str, path: str, json_body: dict = None) -> dict:
    """Forward a request to the Vendor Caller EC2 server and return JSON."""
    url = f"{VENDOR_CALLER_URL}{path}"
    print(f"🔄 Proxying {method} → {url}")

    try:
        if method == "GET":
            resp = requests.get(url, timeout=30, verify=False)
        else:
            resp = requests.post(url, json=json_body, timeout=60, verify=False)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Vendor Caller proxy error: {e}")
        raise


@app.route("/api/call-vendor", methods=["POST"])
@app.route("/api/call-vendor-v2", methods=["POST"])
def call_vendor():
    """Initiate AI vendor call via EC2 Vendor Caller server"""
    try:
        data = request.json

        # Build the payload that cloud_server.py's /api/initiate-call expects
        ec2_payload = {
            "vendor_name": data.get("vendor_name", "the vendor"),
            "vendor_phone": data.get("vendor_phone"),
            "contact_person": data.get("contact_person", "there"),
            "product_name": data.get("product_name", "products"),
            "quantity": data.get("quantity", 0),
            "po_number": data.get("po_number", "N/A"),
            "items": data.get("items", []),
            "total_amount": data.get("total_amount", 0),
            "delivery_date": data.get("delivery_date", "as soon as possible"),
            "category": data.get("category", ""),
        }

        result = _proxy_to_vendor_caller("POST", "/api/initiate-call", ec2_payload)

        # Store metadata locally too (for transcript/logs endpoints + notification)
        call_sid = result.get("call_sid", "")
        if call_sid:
            call_metadata_store[call_sid] = {
                "vendor_name": data.get("vendor_name"),
                "contact_person": data.get("contact_person", "there"),
                "product_name": data.get("product_name"),
                "quantity": data.get("quantity"),
                "po_number": data.get("po_number"),
                "items": data.get("items", []),
                "total_amount": data.get("total_amount", 0),
                "delivery_date": data.get("delivery_date", "as soon as possible"),
            }

        # Return in the format the frontend expects
        return jsonify({
            "success": result.get("status") in ("success", "call_initiated") or result.get("success", False),
            "call_sid": call_sid,
            "order_id": result.get("order_id", ""),
            "status": "initiated",
            "final_status": "initiated",
            "message": "Nova Sonic AI call initiated via EC2 server",
            "websocket_url": result.get("websocket_url", ""),
            "call_context": result.get("call_context", ec2_payload),
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/get-call-status/<call_sid>", methods=["GET"])
def get_call_status(call_sid):
    """Get call status — query EC2 order chain for reliable status tracking.

    The EC2 vendor caller tracks the full order chain (including fallback calls)
    so we rely on it rather than Twilio directly. This also avoids needing the
    twilio Python package in the Lambda.
    """
    try:
        # Step 1: Get call metadata from EC2 (contains order_id)
        meta = {}
        try:
            meta = _proxy_to_vendor_caller("GET", f"/api/call-metadata/{call_sid}")
        except Exception:
            pass

        order_id = meta.get("order_id", "")

        # Step 2: Check order chain status on EC2
        if order_id:
            try:
                chain_resp = _proxy_to_vendor_caller("GET", f"/api/call-status/{order_id}")
                chain = chain_resp.get("order_chain", {})
                chain_status = chain.get("status", "")
                current_decision = chain.get("current_decision", "PENDING")

                if chain_status == "FULFILLED":
                    return jsonify({"success": True, "status": "completed", "final_status": "completed"})
                elif chain_status == "FAILED":
                    return jsonify({"success": True, "status": "completed", "final_status": "completed"})
                elif chain_status in ("CALLING", "FALLBACK_IN_PROGRESS"):
                    attempt = chain.get("attempt_number", 1)
                    vendors_tried = chain.get("vendors_tried", [])
                    fallback_info = None
                    if attempt > 1:
                        fallback_info = {
                            "is_fallback": True,
                            "attempt": attempt,
                            "previous_vendor_rejected": vendors_tried[-2] if len(vendors_tried) >= 2 else "Vendor",
                        }
                    resp = {"success": True, "status": "in-progress"}
                    if fallback_info:
                        resp["fallback_info"] = fallback_info
                    return jsonify(resp)
                else:
                    # PENDING or other — still in progress
                    return jsonify({"success": True, "status": "in-progress"})
            except Exception as chain_err:
                print(f"Order chain check failed: {chain_err}")

        # Step 3: Fallback — check transcript on EC2 for this call_sid
        try:
            ec2_transcript = _proxy_to_vendor_caller("GET", f"/api/transcript/{call_sid}")
            if ec2_transcript.get("success"):
                ec2_decision = ec2_transcript.get("decision", "")
                if ec2_decision == "YES":
                    return jsonify({"success": True, "status": "completed", "final_status": "completed"})
                # For NO, don't return completed — a fallback might be in progress
                # (Step 2 chain check may have failed). Keep polling.
        except Exception:
            pass

        # Step 4: If nothing works, report in-progress
        return jsonify({"success": True, "status": "in-progress"})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/get-call-metadata/<call_sid>", methods=["GET"])
def get_call_metadata(call_sid):
    """Get call metadata — check local store first, then EC2"""
    meta = call_metadata_store.get(call_sid)
    if meta:
        return jsonify({"success": True, **meta})

    try:
        result = _proxy_to_vendor_caller("GET", f"/api/call-metadata/{call_sid}")
        return jsonify({"success": True, **result})
    except Exception:
        return jsonify({"success": False, "error": "Call metadata not found"}), 404


@app.route("/api/store-transcript", methods=["POST"])
def store_transcript():
    """Store transcript — store locally AND forward to EC2"""
    try:
        data = request.json
        call_sid = data.get("call_sid", "")
        conversation_history = data.get("conversation_history", [])
        decision = data.get("decision", "UNKNOWN")

        # Format transcript
        formatted = []
        for msg in conversation_history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                text = content[0].get("text", "") if content else ""
            elif isinstance(content, str):
                text = content
            else:
                text = str(content)

            label = "🤖 AI" if role == "assistant" else "👤 Vendor" if role == "user" else f"👤 {role.title()}"
            if text:
                formatted.append(f"{label}: {text}")

        transcript_text = "\n".join(formatted)

        if call_sid:
            call_transcripts_store[call_sid] = {
                "transcript": transcript_text,
                "conversation_history": conversation_history,
                "decision": decision,
                "stored_at": datetime.now().isoformat(),
            }

        # Also forward to EC2 so it can handle vendor fallback
        try:
            _proxy_to_vendor_caller("POST", "/api/store-transcript", data)
        except Exception as fwd_err:
            print(f"⚠️  Forward to EC2 failed (non-fatal): {fwd_err}")

        return jsonify({
            "success": True,
            "transcript_length": len(transcript_text),
            "decision": decision,
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/get-transcript/<call_sid>", methods=["GET"])
def get_transcript(call_sid):
    """Get transcript — check local store first, then EC2.

    When a transcript with a decision is found, build a ``notification``
    object so the frontend can store it in localStorage and show it in
    the Notifications panel.
    """
    stored = call_transcripts_store.get(call_sid, {})
    transcript = stored.get("transcript", "")
    decision = stored.get("decision")
    conversation_history = stored.get("conversation_history", [])

    # Re-fetch from EC2 if we have no transcript OR if the local decision is
    # NO/UNKNOWN (a fallback call may have updated the transcript on EC2 to YES).
    should_refetch = not transcript or decision in ("NO", "UNKNOWN")
    if should_refetch:
        try:
            result = _proxy_to_vendor_caller("GET", f"/api/transcript/{call_sid}")
            if result.get("success"):
                ec2_transcript = result.get("transcript", "")
                ec2_decision = result.get("decision")
                ec2_history = result.get("conversation_history", [])
                # Only update if EC2 has a transcript and a better decision
                if ec2_transcript and (not transcript or ec2_decision != decision):
                    transcript = ec2_transcript
                    decision = ec2_decision
                    conversation_history = ec2_history
                    call_transcripts_store[call_sid] = {
                        "transcript": transcript,
                        "decision": decision,
                        "conversation_history": conversation_history,
                        "stored_at": result.get("stored_at", datetime.now().isoformat()),
                    }
        except Exception:
            pass

    if not transcript:
        return jsonify({
            "success": False,
            "call_sid": call_sid,
            "transcript": None,
            "message": "Transcript not available yet",
        })

    # Check the EC2 order chain for fallback status and rejected vendors.
    # This runs for ALL decisions because EC2 may have already updated the
    # transcript to YES (after fallback), so we need to collect rejection
    # info regardless of the current decision value.
    rejected_vendors_info = []   # list of (vendor_name, rejection_reason, call_sid)
    try:
        meta_resp = _proxy_to_vendor_caller("GET", f"/api/call-metadata/{call_sid}")
        order_id = meta_resp.get("order_id", "")
        if order_id:
            chain_resp = _proxy_to_vendor_caller("GET", f"/api/call-status/{order_id}")
            _order_chain = chain_resp.get("order_chain", {})
            chain_status = _order_chain.get("status", "")
            all_sids = _order_chain.get("call_sids", [])
            vendors_tried = _order_chain.get("vendors_tried", [])

            if chain_status in ("CALLING", "FALLBACK_IN_PROGRESS"):
                # Fallback still running — withhold result so frontend keeps polling
                print(f"   Fallback in progress for {call_sid}, withholding result")
                return jsonify({
                    "success": True,
                    "call_sid": call_sid,
                    "transcript": None,
                    "decision": None,
                    "message": "Vendor rejected, calling next vendor...",
                })

            # Collect rejection notifications for all vendors that said NO
            # (all vendors except the last one in a FULFILLED chain)
            if chain_status == "FULFILLED" and len(vendors_tried) > 1:
                for i, v_name in enumerate(vendors_tried[:-1]):
                    v_sid = all_sids[i] if i < len(all_sids) else ""
                    rej_reason = "Vendor declined the order"
                    try:
                        v_transcript = _proxy_to_vendor_caller("GET", f"/api/transcript/{v_sid}")
                        if v_transcript.get("success"):
                            rej_reason = _extract_rejection_reason_cloud(v_transcript.get("transcript", ""))
                    except Exception:
                        pass
                    rejected_vendors_info.append((v_name, rej_reason, v_sid))
    except Exception as chain_err:
        print(f"   Order chain check in get-transcript failed: {chain_err}")

    # Build notification when we have a transcript with a decision
    notification = None
    if decision and decision != "PENDING":
        meta = call_metadata_store.get(call_sid, {})

        # Lambda is stateless — always fetch metadata from EC2 if local is empty
        if not meta:
            try:
                ec2_meta = _proxy_to_vendor_caller("GET", f"/api/call-metadata/{call_sid}")
                if ec2_meta.get("vendor_name"):
                    meta = {k: v for k, v in ec2_meta.items() if k != "success"}
            except Exception:
                pass

        # Fetch items from EC2 order chain if not in metadata
        if not meta.get("items"):
            try:
                _oid = meta.get("order_id", "")
                if not _oid:
                    _ec2m = _proxy_to_vendor_caller("GET", f"/api/call-metadata/{call_sid}")
                    _oid = _ec2m.get("order_id", "")
                if _oid:
                    _chain_r = _proxy_to_vendor_caller("GET", f"/api/call-status/{_oid}")
                    _od = _chain_r.get("order_chain", {}).get("order_details", {})
                    if _od.get("items"):
                        meta["items"] = _od["items"]
                    if _od.get("total_amount"):
                        meta.setdefault("total_amount", _od["total_amount"])
                    if _od.get("delivery_date"):
                        meta.setdefault("delivery_date", _od["delivery_date"])
            except Exception:
                pass

        # If a fallback happened, the fulfilling vendor's info is on EC2.
        # Try to get it from the order chain's latest call metadata.
        if decision == "YES":
            try:
                ec2_meta = _proxy_to_vendor_caller("GET", f"/api/call-metadata/{call_sid}")
                order_id = ec2_meta.get("order_id", "")
                if order_id:
                    chain_resp = _proxy_to_vendor_caller("GET", f"/api/call-status/{order_id}")
                    chain = chain_resp.get("order_chain", {})
                    # Get the last call_sid in the chain — that's the one that said YES
                    all_sids = chain.get("call_sids", [])
                    if all_sids and all_sids[-1] != call_sid:
                        last_sid = all_sids[-1]
                        fallback_meta = _proxy_to_vendor_caller("GET", f"/api/call-metadata/{last_sid}")
                        if fallback_meta.get("success", False) or fallback_meta.get("vendor_name"):
                            # Use the fallback vendor's metadata but keep items
                            saved_items = meta.get("items", [])
                            meta = {k: v for k, v in fallback_meta.items() if k != "success"}
                            if not meta.get("items") and saved_items:
                                meta["items"] = saved_items
            except Exception as chain_err:
                print(f"Fallback metadata lookup failed (non-fatal): {chain_err}")

        vendor_name = meta.get("vendor_name", "Vendor")
        contact_person = meta.get("contact_person", "there")
        po_number = meta.get("po_number", f"PO-{call_sid[:8]}")
        items = meta.get("items", [])
        total_amount = meta.get("total_amount", 0)
        delivery_date = meta.get("delivery_date", "as soon as possible")
        product_name = meta.get("product_name", "products")

        # Prices are already in INR — no conversion needed
        inr_rate = 1.0
        total_inr = round(float(total_amount), 2) if total_amount else 0

        # Build items summary for email
        items_lines = ""
        for i, item in enumerate(items, 1):
            item_name = item.get("name", "Item")
            item_qty = item.get("quantity", 0)
            item_price = item.get("unit_price", 0)
            item_inr = round(float(item_price), 2)
            item_total = round(item_inr * item_qty, 2)
            items_lines += f"    {i}. {item_name} — Qty: {item_qty}, Unit Price: ₹{item_inr:,.2f}, Line Total: ₹{item_total:,.2f}\n"
        if not items_lines:
            items_lines = f"    1. {product_name}\n"

        today_str = datetime.now().strftime("%B %d, %Y")

        if decision == "YES":
            subject = f"Purchase Order {po_number} — Confirmation & PO Document | HeartKart"
            body = (
                f"Dear {contact_person},\n\n"
                f"Thank you for taking the time to speak with us today and for confirming "
                f"your ability to fulfill our purchase order. We truly value our partnership "
                f"with {vendor_name} and look forward to continued collaboration.\n\n"
                f"As discussed during our call, please find the order details below:\n\n"
                f"ORDER SUMMARY\n"
                f"{'=' * 50}\n"
                f"  PO Number      : {po_number}\n"
                f"  Order Date     : {today_str}\n"
                f"  Delivery Date  : {delivery_date}\n"
                f"  Payment Terms  : Net 30\n\n"
                f"ITEMS ORDERED\n"
                f"{'-' * 50}\n"
                f"{items_lines}\n"
                f"  Grand Total    : ₹{total_inr:,.2f}\n"
                f"{'=' * 50}\n\n"
                f"The official Purchase Order document is attached to this email as a PDF "
                f"for your records. Please review the document and confirm receipt at your "
                f"earliest convenience.\n\n"
                f"Should you have any questions regarding specifications, delivery logistics, "
                f"or payment terms, please do not hesitate to reach out to us directly.\n\n"
                f"We appreciate your prompt attention to this order and look forward to "
                f"receiving the shipment as scheduled.\n\n"
                f"Warm regards,\n\n"
                f"Priya Sharma\n"
                f"Procurement Manager\n"
                f"HeartKart Pvt. Ltd.\n"
                f"procurement@heartkart.com | +91 80-4567-8900"
            )

            # Generate PO PDF
            pdf_url = _generate_po_pdf(po_number, vendor_name, contact_person,
                                       items, total_amount, delivery_date, inr_rate)

            notification = {
                "id": f"notif-{call_sid}",
                "po_number": po_number,
                "vendor_name": vendor_name,
                "call_sid": call_sid,
                "call_duration": 0,
                "subject": subject,
                "body": body,
                "pdf_url": pdf_url,
                "created_at": datetime.now().isoformat(),
                "status": "pending",
                "type": "vendor_call_success",
                "order_status": "pending_email",
                "product_name": product_name,
                "metadata": {
                    "contact_person": contact_person,
                    "delivery_date": delivery_date,
                    "total_amount": total_amount,
                    "items": items,
                    "call_transcript": transcript,
                },
            }
            # Embed rejection notifications so the frontend can extract them
            if rejected_vendors_info:
                notification["rejected_vendors"] = [
                    {"vendor_name": rv[0], "rejection_reason": rv[1], "call_sid": rv[2]}
                    for rv in rejected_vendors_info
                ]
        else:
            # NO or UNKNOWN — rejection notification (no PO, no email generated)
            rejection_reason = _extract_rejection_reason_cloud(transcript)
            notification = {
                "id": f"notif-reject-{call_sid[:8]}",
                "type": "vendor_call_rejection",
                "timestamp": datetime.now().isoformat(),
                "title": f"Vendor Rejected: {vendor_name}",
                "message": f"{vendor_name} rejected the order for {product_name}. Reason: {rejection_reason}",
                "po_number": "N/A",
                "vendor_name": vendor_name,
                "product_name": product_name,
                "call_sid": call_sid,
                "call_duration": 0,
                "subject": f"Vendor Rejected: {vendor_name} - {rejection_reason}",
                "body": (
                    f"Vendor {vendor_name} was contacted for {product_name} "
                    f"(qty: {sum(i.get('quantity', 0) for i in items) if items else 'N/A'}) "
                    f"but declined the order.\n\n"
                    f"Rejection reason: {rejection_reason}\n\n"
                    f"The system is automatically contacting the next available vendor."
                ),
                "pdf_url": "",
                "created_at": datetime.now().isoformat(),
                "status": "failed",
                "order_status": "rejected",
                "rejection_reason": rejection_reason,
                "priority": "high",
                "actions": [{"label": "View Call Log", "action": "view_call_logs"}],
                "metadata": {
                    "contact_person": contact_person,
                    "delivery_date": delivery_date,
                    "total_amount": total_amount,
                    "items": items,
                    "call_transcript": transcript,
                },
            }

    # Build rejection notifications for vendors that said NO (when fallback succeeded)
    extra_notifications = []
    product_name_for_rej = call_metadata_store.get(call_sid, {}).get("product_name", "products")
    if not product_name_for_rej:
        try:
            _m = _proxy_to_vendor_caller("GET", f"/api/call-metadata/{call_sid}")
            product_name_for_rej = _m.get("product_name", "products")
        except Exception:
            product_name_for_rej = "products"
    for rej_vendor, rej_reason, rej_sid in rejected_vendors_info:
        extra_notifications.append({
            "id": f"notif-reject-{rej_sid[:8] if rej_sid else call_sid[:8]}",
            "type": "vendor_call_rejection",
            "timestamp": datetime.now().isoformat(),
            "title": f"Vendor Rejected: {rej_vendor}",
            "message": f"{rej_vendor} rejected the order. Reason: {rej_reason}",
            "po_number": "N/A",
            "vendor_name": rej_vendor,
            "product_name": product_name_for_rej,
            "call_sid": rej_sid or call_sid,
            "call_duration": 0,
            "subject": f"Vendor Rejected: {rej_vendor} - {rej_reason}",
            "body": f"Vendor {rej_vendor} was contacted but declined the order.\n\nRejection reason: {rej_reason}",
            "pdf_url": "",
            "created_at": datetime.now().isoformat(),
            "status": "failed",
            "order_status": "rejected",
            "rejection_reason": rej_reason,
        })

    resp = {
        "success": True,
        "call_sid": call_sid,
        "transcript": transcript,
        "decision": decision,
        "conversation_history": conversation_history,
        "notification": notification,
        "stored_at": stored.get("stored_at") or call_transcripts_store.get(call_sid, {}).get("stored_at"),
    }
    if extra_notifications:
        resp["extra_notifications"] = extra_notifications
    return jsonify(resp)


@app.route("/api/call-logs", methods=["GET"])
def get_call_logs():
    """Get call logs — use Twilio if available, else EC2"""
    try:
        if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
            from twilio.rest import Client
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            calls = client.calls.list(limit=50)

            call_logs = []
            for call in calls:
                recordings = client.recordings.list(call_sid=call.sid, limit=1)
                recording_url = (
                    f"https://api.twilio.com{recordings[0].uri.replace('.json', '.mp3')}"
                    if recordings
                    else None
                )
                metadata = call_metadata_store.get(call.sid, {})
                stored_transcript = call_transcripts_store.get(call.sid, {})

                call_logs.append({
                    "call_sid": call.sid,
                    "vendor_name": metadata.get("vendor_name", "Vendor"),
                    "vendor_phone": call.to,
                    "status": call.status,
                    "duration": call.duration or 0,
                    "started_at": call.start_time.isoformat() if call.start_time else None,
                    "ended_at": call.end_time.isoformat() if call.end_time else None,
                    "transcript": stored_transcript.get("transcript"),
                    "recording_url": recording_url,
                    "product_name": metadata.get("product_name"),
                    "quantity": metadata.get("quantity"),
                    "po_number": metadata.get("po_number"),
                })

            return jsonify({"success": True, "calls": call_logs})
        else:
            # Fallback: list from EC2
            result = _proxy_to_vendor_caller("GET", "/api/calls")
            return jsonify({"success": True, "calls": result.get("calls", [])})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# VENDORS LIST (from DynamoDB product catalog)
# ============================================================================

@app.route("/api/vendors/all", methods=["GET"])
def get_all_vendors():
    """Get all vendors from DynamoDB product catalog"""
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from product_data_access import get_all_products

        products = get_all_products(limit=1000)
        vendors_map = {}
        for p in products:
            vname = p.get("vendor_name") or p.get("vendor")
            if vname and vname not in vendors_map:
                vendors_map[vname] = {
                    "name": vname,
                    "phone": p.get("vendor_phone", ""),
                    "email": p.get("vendor_email", ""),
                    "priority": 5,
                }

        vendors = sorted(vendors_map.values(), key=lambda v: (v.get("name") or "").lower())
        return jsonify({"success": True, "vendors": vendors})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# ORDERS (in-memory store)
# ============================================================================

@app.route("/api/orders", methods=["GET"])
def get_orders():
    try:
        sorted_orders = sorted(orders_store, key=lambda o: o.get("created_at", ""), reverse=True)
        return jsonify({"success": True, "orders": sorted_orders})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/orders/mark-sent", methods=["POST"])
def mark_order_sent():
    try:
        data = request.json or {}
        po_number = data.get("po_number")
        if not po_number:
            return jsonify({"success": False, "error": "po_number required"}), 400

        updated = False
        for order in orders_store:
            if order.get("po_number") == po_number:
                order["status"] = "email_sent"
                order["email_sent_at"] = datetime.now().isoformat()
                updated = True
                break

        if not updated:
            # Create the order entry if it doesn't exist
            orders_store.append({
                "po_number": po_number,
                "status": "email_sent",
                "email_sent_at": datetime.now().isoformat(),
                "created_at": datetime.now().isoformat(),
            })

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# ENTRYPOINT
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("🎄 HeartKart Inventory Management API  (AgentCore Cloud Mode)")
    print("=" * 70)
    print(f"\n📍 AWS Region:           {AWS_REGION}")
    print(f"📍 Vendor Caller EC2:    {VENDOR_CALLER_URL}")
    print(f"📍 Twilio configured:    {'✅' if TWILIO_ACCOUNT_SID else '❌'}")
    print(f"\n🤖 AgentCore Agents ({len(AGENT_ARNS)}):")
    for name, arn in AGENT_ARNS.items():
        print(f"   • {name}: {arn.split('/')[-1]}")

    print("\n📊 Replenishment Planner Endpoints:")
    print("  GET  /api/replenishment/plan")
    print("  GET  /api/replenishment/urgent")
    print("  GET  /api/replenishment/by-vendor")
    print("  POST /api/replenishment/export-po")
    print("\n🎯 Stockout Sentinel Endpoints:")
    print("  GET  /api/stockout/report")
    print("  GET  /api/stockout/substitutes/<sku>")
    print("  GET  /api/stockout/critical")
    print("  GET  /api/stockout/by-category")
    print("  POST /api/stockout/substitute-suggestions")
    print("\n💬 Inventory Copilot Endpoints:")
    print("  POST /api/copilot/query")
    print("  GET  /api/copilot/suggestions")
    print("\n🔍 Exception Investigator Endpoints:")
    print("  GET  /api/exceptions/investigate")
    print("  GET  /api/exceptions/summary")
    print("  GET  /api/exceptions/by-type/<type>")
    print("\n🏷️  Markdown & Clearance Coach Endpoints:")
    print("  GET  /api/markdown/report")
    print("  GET  /api/markdown/aged-inventory")
    print("  GET  /api/markdown/timeline")
    print("  GET  /api/markdown/bundles")
    print("  GET  /api/markdown/summary")
    print("\n📈 Market Intelligence Endpoints:")
    print("  GET/POST /api/market-intelligence")
    print("\n💰 Pricing Intelligence Endpoints:")
    print("  GET/POST /api/pricing-intelligence")
    print("\n📧 Email Drafter Endpoints:")
    print("  POST /api/draft-email")
    print("\n📞 Vendor Calling Endpoints:")
    print("  POST /api/call-vendor")
    print("  POST /api/call-vendor-v2")
    print("  GET  /api/get-call-status/<call_sid>")
    print("  GET  /api/get-call-metadata/<call_sid>")
    print("  POST /api/store-transcript")
    print("  GET  /api/get-transcript/<call_sid>")
    print("  GET  /api/call-logs")
    print("\n📦 Other Endpoints:")
    print("  GET  /api/inventory")
    print("  GET  /api/vendors/all")
    print("  GET  /api/orders")
    print("  POST /api/orders/mark-sent")
    print("  GET  /api/health")
    print(f"\n🌐 Running on http://localhost:5000")
    print("=" * 70)

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=os.getenv("FLASK_DEBUG") == "1",
        threaded=True,
    )
