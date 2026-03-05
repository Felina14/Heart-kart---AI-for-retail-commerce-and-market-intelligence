#!/usr/bin/env python3
"""
HeartKart Inventory Management API
Unified backend for all inventory agents and operations
"""

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import importlib.util
import sys
import os
import io
import time
import threading
from datetime import datetime

# Add agent directories to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'agents', 'replenishment_planner'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'agents', 'stockout_sentinel'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'agents', 'inventory_copilot'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'agents', 'exception_investigator'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'agents', 'markdown_coach'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'agents', 'market_intelligence'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'agents', 'pricing_intelligence'))

# Import agent functions
from replenishment_planner_agent import generate_replenishment_plan
from pdf_generator_v2 import create_po_pdf
from stockout_sentinel_agent import generate_stockout_report, get_substitute_for_product
from inventory_copilot_agent import execute_inventory_query, get_query_suggestions
from exception_investigator_agent import investigate_exceptions
from markdown_coach_agent import MarkdownCoachAgent, generate_markdown_report
from market_intelligence_agent import (
    generate_market_intelligence_report as _mi_generate_report,
    get_competitor_price_index as _mi_competitor_price_index,
    get_regional_demand_trends as _mi_regional_demand_trends,
    get_category_trend_signals as _mi_category_trend_signals,
)
from pricing_intelligence_agent import (
    generate_pricing_intelligence_report as _pi_generate_report,
    calculate_recommended_price_range as _pi_recommended_price_range,
    get_competitor_price_comparison as _pi_competitor_comparison,
    calculate_demand_impact as _pi_demand_impact,
    get_price_optimization_recommendations as _pi_optimization_recs,
)

app = Flask(__name__)
CORS(app)

# ----------------------------------------------------------------------------
# Utilities
# ----------------------------------------------------------------------------

def _load_module_from_file(module_name: str, file_path: str):
    """
    Load a Python module from an explicit file path. This avoids import name
    collisions (e.g. multiple different `agent.py` files in the repo).
    """
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module {module_name} from {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# In-memory store for call metadata
call_metadata_store = {}

# In-memory store for call transcripts
call_transcripts_store = {}

# In-memory store for order chains (tracks vendor fallback attempts)
# Key: order_id → { order_details, vendors_tried, attempt_number, max_attempts }
order_chains = {}

# In-memory store for notifications (keyed by call_sid)
notifications_store = {}


def _extract_rejection_reason(transcript: str) -> str:
    """Extract the vendor's rejection reason from the call transcript."""
    if not transcript:
        return 'Vendor declined the order'

    transcript_lower = transcript.lower()

    # Common rejection keywords and their associated reasons
    reason_keywords = [
        ('out of stock', 'Out of stock'),
        ('no stock', 'No stock available'),
        ('not available', 'Product not available'),
        ('cannot fulfill', 'Cannot fulfill the order'),
        ("can't fulfill", 'Cannot fulfill the order'),
        ('don\'t have', 'Does not have the product'),
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
        # Remove role prefix
        text = last_vendor_line.split(':', 1)[-1].strip() if ':' in last_vendor_line else last_vendor_line
        if len(text) > 10 and len(text) < 200:
            return text

    return 'Vendor declined the order'


def _find_alternative_vendor(category: str, vendors_tried: list) -> dict | None:
    """
    Find an alternative vendor for the same product category.
    Queries DynamoDB for products in the same category and returns
    the first vendor that hasn't been tried yet.
    """
    try:
        from product_data_access import get_products_by_category
        products = get_products_by_category(category, limit=200)

        # Collect unique vendors we haven't tried yet
        seen = set(vendors_tried)
        for p in products:
            vname = p.get('vendor_name') or p.get('vendor')
            vphone = p.get('vendor_phone', '')
            if vname and vname not in seen and vphone:
                return {
                    'vendor_name': vname,
                    'vendor_phone': vphone,
                    'vendor_email': p.get('vendor_email', ''),
                    'contact_person': 'Purchasing Manager',
                }
        return None
    except Exception as e:
        print(f"⚠️  Error finding alternative vendor: {e}")
        return None


def _initiate_fallback_call(order_id: str):
    """
    Background helper: initiate a call to the next vendor for a given order.
    Called automatically when a vendor declines.
    """
    import threading

    def _do_call():
        try:
            chain = order_chains.get(order_id)
            if not chain:
                print(f"⚠️  No order chain found for {order_id}")
                return

            if chain['attempt_number'] >= chain['max_attempts']:
                print(f"⏹️  Max attempts ({chain['max_attempts']}) reached for order {order_id}")
                return

            category = chain.get('category', '')
            alt = _find_alternative_vendor(category, chain['vendors_tried'])
            if not alt:
                print(f"⚠️  No alternative vendor found for category '{category}'")
                return

            print(f"\n🔄 VENDOR FALLBACK: Calling {alt['vendor_name']} for order {order_id}")

            from twilio.rest import Client
            TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
            TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
            TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
            NGROK_URL = os.getenv('NGROK_URL', '')

            websocket_url = f"wss://{NGROK_URL.replace('https://', '').replace('http://', '')}/media-stream"

            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{websocket_url}" />
    </Connect>
</Response>"""

            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            call = client.calls.create(
                twiml=twiml,
                to=alt['vendor_phone'],
                from_=TWILIO_PHONE_NUMBER,
                record=True,
            )

            # Update order chain
            chain['attempt_number'] += 1
            chain['vendors_tried'].append(alt['vendor_name'])
            chain['current_call_sid'] = call.sid

            # Build context for the new call
            od = chain['order_details']
            call_context = {
                'call_id': call.sid,
                'vendor_name': alt['vendor_name'],
                'contact_person': alt['contact_person'],
                'product_name': od.get('product_name', 'products'),
                'quantity': od.get('quantity', 0),
                'po_number': od.get('po_number', 'N/A'),
                'items': od.get('items', []),
                'total_amount': od.get('total_amount', 0),
                'delivery_date': od.get('delivery_date', 'as soon as possible'),
            }

            call_metadata_store[call.sid] = {
                'vendor_name': alt['vendor_name'],
                'product_name': od.get('product_name'),
                'quantity': od.get('quantity'),
                'po_number': od.get('po_number'),
                'order_id': order_id,
            }
            call_metadata_store[call.sid].update(call_context)

            print(f"✅ Fallback call initiated: {call.sid} → {alt['vendor_name']} ({alt['vendor_phone']})")

        except Exception as e:
            print(f"❌ Error initiating fallback call: {e}")
            import traceback
            traceback.print_exc()

    # Small delay before calling next vendor to let the previous call fully tear down
    import time

    def _delayed_call():
        time.sleep(5)
        _do_call()

    t = threading.Thread(target=_delayed_call, daemon=True)
    t.start()

# ----------------------------------------------------------------------------
# Simple in-memory caching (demo/dev)
# ----------------------------------------------------------------------------

_pricing_cache = {}  # key -> {"ts": float, "payload": dict}

def _cache_get(cache: dict, key: str, ttl_seconds: int) -> dict | None:
    try:
        entry = cache.get(key)
        if not entry:
            return None
        if (time.time() - float(entry.get("ts", 0))) > ttl_seconds:
            return None
        return entry.get("payload")
    except Exception:
        return None

def _cache_set(cache: dict, key: str, payload: dict):
    cache[key] = {"ts": time.time(), "payload": payload}

def _run_with_timeout(fn, timeout_seconds: int):
    """
    Run a function with a timeout. If it doesn't finish, return (False, None).
    Note: we can't force-kill the underlying work; we just stop waiting.
    """
    result = {"value": None, "ok": False}

    def _target():
        try:
            result["value"] = fn()
            result["ok"] = True
        except Exception as e:
            result["value"] = e
            result["ok"] = False

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout_seconds)
    return result["ok"], result["value"]

def _pricing_fallback_payload(analysis_type: str, sku: str | None, category: str | None) -> dict:
    """
    Fast, local fallback so the UI always renders even if AWS calls are slow.
    """
    sys.path.insert(0, os.path.dirname(__file__))
    from product_data_access import get_all_products

    products = get_all_products(limit=80)
    # Pick a stable sample
    sample = [p for p in products if p.get("sku")][:25]

    # Build lightweight optimization recommendations
    recs = []
    for p in sample[:20]:
        price = float(p.get("price", 0) or 0)
        if price <= 0:
            continue
        # Very simple heuristic-based "recommendation"
        sales_vel = float(p.get("sales_velocity", 1.0) or 1.0)
        stock = int(p.get("stock_quantity", p.get("inventory", 0)) or 0)
        # Higher stock + low velocity -> consider decrease, else maintain/increase
        if stock > 60 and sales_vel < 1.0:
            action = "CONSIDER_DECREASE"
            pct = -round(min(15.0, max(5.0, (stock - 60) * 0.2)), 1)
        elif stock < 15 and sales_vel > 1.2:
            action = "CONSIDER_INCREASE"
            pct = round(min(12.0, max(3.0, (15 - stock) * 0.6)), 1)
        else:
            action = "MAINTAIN_PRICE"
            pct = 0.0

        recommended_price = round(price * (1 + pct / 100), 2)
        recs.append({
            "sku": p.get("sku"),
            "product_name": p.get("name"),
            "category": p.get("category", "Uncategorized"),
            "current_price": price,
            "recommended_price": recommended_price,
            "price_change": round(recommended_price - price, 2),
            "price_change_pct": pct,
            "current_margin": round(20 + (price % 10), 2),
            "competitiveness": "COMPETITIVE",
            "expected_revenue_change_pct": round(pct * 0.7, 1),
            "expected_margin_change_pct": round(max(0.0, pct * 0.5), 1),
            "recommendation": action,
            "priority_score": int(abs(pct) * 4),
            "reason": "Fast demo estimate (fallback mode)."
        })

    increase_price = len([r for r in recs if "INCREASE" in r["recommendation"]])
    decrease_price = len([r for r in recs if "DECREASE" in r["recommendation"]])
    maintain_price = len([r for r in recs if r["recommendation"] == "MAINTAIN_PRICE"])
    avg_price_change_pct = round(sum(r["price_change_pct"] for r in recs) / max(1, len(recs)), 2)
    total_revenue_impact = round(sum(r["expected_revenue_change_pct"] for r in recs) / max(1, len(recs)), 2)

    payload = {
        "status": "success",
        "report_date": datetime.now().isoformat(),
        "analysis_type": analysis_type,
        "guardrails": {
            "guardrails": {
                "min_margin_percent": 15.0,
                "max_discount_percent": 40.0,
                "competitive_price_tolerance": 5.0,
            }
        },
        "optimization_recommendations": {
            "category": category or "All Categories",
            "total_recommendations": len(recs),
            "summary": {
                "increase_price": increase_price,
                "decrease_price": decrease_price,
                "maintain_price": maintain_price,
                "avg_price_change_pct": avg_price_change_pct,
                "total_revenue_impact_pct": total_revenue_impact,
            },
            "recommendations": recs,
        },
        "ai_insights": None,  # Don't show fallback message - let frontend handle missing AI insights
    }

    # If the caller is asking for a specific view, keep response minimal-but-valid
    if analysis_type == "price_range" and sku:
        # Provide a small stub price_range so the panel can render
        product = next((p for p in products if p.get("sku") == sku), None) or {}
        price = float(product.get("price", 0) or 0)
        payload["price_range"] = {
            "sku": sku,
            "product_name": product.get("name", "Product"),
            "category": product.get("category", "Uncategorized"),
            "current_price": price,
            "cost_price": round(price * 0.65, 2) if price else 0,
            "current_margin_percent": 20.0,
            "competitor_price": round(price * 1.03, 2) if price else 0,
            "price_range": {"min_price": round(price * 0.92, 2), "optimal_price": round(price * 1.02, 2), "max_price": round(price * 1.08, 2)},
            "guardrails": payload["guardrails"]["guardrails"],
            "recommendation": {
                "action": "MAINTAIN_PRICE",
                "reason": "Fallback mode estimate.",
                "suggested_price": round(price * 1.02, 2),
                "price_change": round(price * 0.02, 2),
                "price_change_percent": 2.0,
            },
        }
    return payload

# ============================================================================
# REPLENISHMENT PLANNER ENDPOINTS
# ============================================================================

@app.route('/api/replenishment/plan', methods=['GET'])
def get_replenishment_plan():
    """
    Generate replenishment plan
    Query params:
    - threshold: Stock threshold (default: 20)
    - format: 'summary' or 'full' (default: 'full')
    """
    try:
        threshold = int(request.args.get('threshold', 20))
        format_type = request.args.get('format', 'full')
        include_ai = str(request.args.get('include_ai', 'true')).strip().lower() not in {'0', 'false', 'no', 'off'}
        
        # Default to AI-enabled for richer demo experience; disable via ?include_ai=false
        plan = generate_replenishment_plan(threshold=threshold, include_ai=(include_ai and format_type != 'summary'))
        
        if format_type == 'summary':
            return jsonify({
                'status': plan['status'],
                'generated_at': plan['generated_at'],
                'summary': plan['summary'],
                'top_priorities': plan['recommendations'][:5]
            })
        
        return jsonify(plan)
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/replenishment/urgent', methods=['GET'])
def get_urgent_reorders():
    """Get only CRITICAL and HIGH urgency items"""
    try:
        plan = generate_replenishment_plan(include_ai=False)
        
        urgent = [r for r in plan['recommendations'] if r['urgency'] in ['CRITICAL', 'HIGH']]
        
        return jsonify({
            'status': 'success',
            'count': len(urgent),
            'urgent_reorders': urgent
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/replenishment/by-vendor', methods=['GET'])
def get_reorders_by_vendor():
    """Group reorder recommendations by vendor"""
    try:
        plan = generate_replenishment_plan(include_ai=False)
        
        by_vendor = {}
        for rec in plan['recommendations']:
            vendor = rec['vendor']
            if vendor not in by_vendor:
                by_vendor[vendor] = {
                    'vendor_name': vendor,
                    'total_items': 0,
                    'total_cost': 0,
                    'items': []
                }
            
            by_vendor[vendor]['total_items'] += 1
            by_vendor[vendor]['total_cost'] += rec['estimated_cost']
            by_vendor[vendor]['items'].append(rec)
        
        return jsonify({
            'status': 'success',
            'vendors': list(by_vendor.values())
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/replenishment/export-po', methods=['POST'])
def export_purchase_order():
    """Export purchase order for selected items as PDF"""
    try:
        data = request.get_json()
        
        # Support both 'skus' (from replenishment panel) and 'items' (from call vendor modal)
        skus = data.get('skus', [])
        items = data.get('items', [])
        
        if items:
            # Items provided directly (from call vendor modal)
            # Normalize items to match expected format
            selected = []
            for item in items:
                normalized = {
                    'sku': item.get('sku', f"SKU-{item.get('name', 'UNKNOWN').replace(' ', '-')}"),
                    'name': item.get('name', 'Unknown Item'),
                    'category': item.get('category', 'general'),
                    'recommended_order_qty': item.get('quantity', 1),
                    'vendor': item.get('vendor', 'Unknown Vendor'),
                    'lead_time_days': item.get('lead_time_days', 7),
                    'estimated_cost': item.get('estimated_cost', item.get('quantity', 1) * item.get('unit_price', 0))
                }
                selected.append(normalized)
        elif skus:
            # SKUs provided (from replenishment panel)
            plan = generate_replenishment_plan(include_ai=False)
            selected = [r for r in plan['recommendations'] if r['sku'] in skus]
        else:
            return jsonify({'status': 'error', 'error': 'No items or SKUs provided'}), 400
        
        if not selected:
            return jsonify({'status': 'error', 'error': 'No items selected'}), 400
        
        po = {
            'po_number': f"PO-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            'date': datetime.now().isoformat(),
            'items': selected,
            'total_items': len(selected),
            'total_cost': sum(item.get('estimated_cost', 0) for item in selected)
        }
        
        pdf_bytes = create_po_pdf(po)
        
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{po['po_number']}.pdf"
        )
        
    except Exception as e:
        import traceback
        print(f"Error generating PO: {e}")
        print(traceback.format_exc())
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================================
# STOCKOUT SENTINEL ENDPOINTS
# ============================================================================

@app.route('/api/stockout/report', methods=['GET'])
def get_stockout_report():
    """
    Generate comprehensive stockout report
    Query params:
    - risk_level: Filter by risk level (CRITICAL, HIGH, MEDIUM, LOW)
    - category: Filter by category
    """
    try:
        risk_level = request.args.get('risk_level', None)
        category = request.args.get('category', None)
        
        report = generate_stockout_report()
        
        if report['status'] != 'success':
            return jsonify(report), 500
        
        # Apply filters
        if risk_level or category:
            filtered_products = report['at_risk_products']
            
            if risk_level:
                filtered_products = [p for p in filtered_products if p['risk_level'] == risk_level.upper()]
            
            if category:
                filtered_products = [p for p in filtered_products if p['category'].lower() == category.lower()]
            
            report['at_risk_products'] = filtered_products
            report['summary']['total_at_risk'] = len(filtered_products)
        
        return jsonify(report)
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/stockout/substitutes/<sku>', methods=['GET'])
def get_substitutes(sku):
    """Get substitute recommendations for a specific product"""
    try:
        result = get_substitute_for_product(sku)
        
        if result['status'] == 'error':
            return jsonify(result), 404
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/stockout/critical', methods=['GET'])
def get_critical_stockouts():
    """Get only critical stockout risks"""
    try:
        report = generate_stockout_report()
        
        if report['status'] != 'success':
            return jsonify(report), 500
        
        critical_products = [p for p in report['at_risk_products'] if p['risk_level'] == 'CRITICAL']
        
        return jsonify({
            'status': 'success',
            'count': len(critical_products),
            'critical_stockouts': critical_products
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/stockout/by-category', methods=['GET'])
def get_stockouts_by_category():
    """Group stockout risks by category"""
    try:
        report = generate_stockout_report()
        
        if report['status'] != 'success':
            return jsonify(report), 500
        
        by_category = {}
        for product in report['at_risk_products']:
            category = product['category']
            if category not in by_category:
                by_category[category] = {
                    'category': category,
                    'total_products': 0,
                    'critical_count': 0,
                    'high_count': 0,
                    'products': []
                }
            
            by_category[category]['total_products'] += 1
            if product['risk_level'] == 'CRITICAL':
                by_category[category]['critical_count'] += 1
            elif product['risk_level'] == 'HIGH':
                by_category[category]['high_count'] += 1
            
            by_category[category]['products'].append(product)
        
        return jsonify({
            'status': 'success',
            'categories': list(by_category.values())
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/stockout/substitute-suggestions', methods=['POST'])
def get_bulk_substitutes():
    """Get substitute suggestions for multiple products"""
    try:
        data = request.get_json()
        skus = data.get('skus', [])
        
        if not skus:
            return jsonify({'status': 'error', 'error': 'No SKUs provided'}), 400
        
        results = []
        for sku in skus:
            result = get_substitute_for_product(sku)
            if result['status'] == 'success':
                results.append(result)
        
        return jsonify({
            'status': 'success',
            'count': len(results),
            'substitutes': results
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================================
# INVENTORY COPILOT ENDPOINTS
# ============================================================================

@app.route('/api/copilot/query', methods=['POST'])
def copilot_query():
    """
    Execute natural language query
    Body: { "query": "Show me wreaths under $50" }
    """
    try:
        data = request.get_json()
        query = data.get('query', '')
        
        if not query:
            return jsonify({'status': 'error', 'error': 'No query provided'}), 400
        
        result = execute_inventory_query(query)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/copilot/suggestions', methods=['GET'])
def copilot_suggestions():
    """Get example queries"""
    try:
        suggestions = get_query_suggestions()
        return jsonify({
            'status': 'success',
            'suggestions': suggestions
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================================
# EXCEPTION INVESTIGATOR ENDPOINTS
# ============================================================================

@app.route('/api/exceptions/investigate', methods=['GET'])
def investigate():
    """
    Investigate exceptions and anomalies
    Query params:
    - days: Number of days to analyze (default: 30)
    - threshold: Z-score threshold (default: 2.0)
    """
    try:
        days = int(request.args.get('days', 30))
        threshold = float(request.args.get('threshold', 2.0))
        
        result = investigate_exceptions(days=days, threshold=threshold)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/exceptions/summary', methods=['GET'])
def exceptions_summary():
    """Get summary of anomalies without full details"""
    try:
        days = int(request.args.get('days', 30))
        threshold = float(request.args.get('threshold', 2.0))
        
        result = investigate_exceptions(days=days, threshold=threshold)
        
        return jsonify({
            'status': result['status'],
            'summary': result['summary'],
            'insights': result['insights'],
            'generated_at': result['generated_at']
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/exceptions/by-type/<anomaly_type>', methods=['GET'])
def exceptions_by_type(anomaly_type):
    """Get anomalies filtered by type (DEMAND_SURGE, DEMAND_DROP, STAGNANT)"""
    try:
        days = int(request.args.get('days', 30))
        threshold = float(request.args.get('threshold', 2.0))
        
        result = investigate_exceptions(days=days, threshold=threshold)
        
        if result['status'] != 'success':
            return jsonify(result), 500
        
        filtered = [a for a in result['anomalies'] if a['anomaly_type'] == anomaly_type.upper()]
        
        return jsonify({
            'status': 'success',
            'anomaly_type': anomaly_type.upper(),
            'count': len(filtered),
            'anomalies': filtered
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================================
# MARKDOWN & CLEARANCE COACH ENDPOINTS
# ============================================================================

@app.route('/api/markdown/report', methods=['GET'])
def get_markdown_report():
    """
    Get complete markdown and clearance report
    Query params:
    - threshold: Age threshold in days (default: 60)
    """
    try:
        report = generate_markdown_report()
        return jsonify(report)
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/markdown/aged-inventory', methods=['GET'])
def get_aged_inventory():
    """
    Get list of aged inventory items
    Query params:
    - threshold: Age threshold in days (default: 60)
    """
    try:
        agent = MarkdownCoachAgent()
        threshold = int(request.args.get('threshold', 60))
        aged = agent.analyze_aged_inventory(age_threshold_days=threshold)
        
        return jsonify({
            'status': 'success',
            'threshold_days': threshold,
            'count': len(aged),
            'aged_products': aged
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/markdown/timeline', methods=['GET'])
def get_clearance_timeline():
    """Get phased clearance timeline"""
    try:
        agent = MarkdownCoachAgent()
        threshold = int(request.args.get('threshold', 60))
        aged = agent.analyze_aged_inventory(age_threshold_days=threshold)
        timeline = agent.get_clearance_timeline(aged)
        
        return jsonify({
            'status': 'success',
            'timeline': timeline
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/markdown/bundles', methods=['GET'])
def get_bundle_suggestions():
    """Get suggested product bundles"""
    try:
        agent = MarkdownCoachAgent()
        threshold = int(request.args.get('threshold', 60))
        aged = agent.analyze_aged_inventory(age_threshold_days=threshold)
        bundles = agent.suggest_bundles(aged)
        
        return jsonify({
            'status': 'success',
            'count': len(bundles),
            'bundles': bundles
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/markdown/summary', methods=['GET'])
def get_markdown_summary():
    """Get summary statistics only"""
    try:
        agent = MarkdownCoachAgent()
        threshold = int(request.args.get('threshold', 60))
        aged = agent.analyze_aged_inventory(age_threshold_days=threshold)
        
        total_aged_value = sum(p['current_price'] * p['quantity'] for p in aged)
        total_potential_revenue = sum(p['markdown_recommendation']['potential_revenue'] for p in aged)
        
        # Group by category
        by_category = {}
        for product in aged:
            cat = product['category']
            if cat not in by_category:
                by_category[cat] = 0
            by_category[cat] += 1
        
        # Group by urgency
        by_urgency = {}
        for product in aged:
            urgency = product['markdown_recommendation']['urgency']
            if urgency not in by_urgency:
                by_urgency[urgency] = 0
            by_urgency[urgency] += 1
        
        return jsonify({
            'status': 'success',
            'summary': {
                'total_aged_items': len(aged),
                'total_aged_value': round(total_aged_value, 2),
                'potential_revenue': round(total_potential_revenue, 2),
                'recovery_rate': round(total_potential_revenue/total_aged_value*100, 1) if total_aged_value > 0 else 0,
                'by_category': by_category,
                'by_urgency': by_urgency
            }
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================================
# VENDOR CALLER ENDPOINTS
# ============================================================================

# Store for call scripts (in production, use DynamoDB)
call_scripts = {}

@app.route('/api/vendor/twiml/<call_id>', methods=['POST', 'GET'])
def vendor_twiml(call_id):
    """Generate TwiML for Twilio to read the script"""
    from flask import Response
    from twilio.twiml.voice_response import VoiceResponse, Gather
    
    # Get the script for this call
    script = call_scripts.get(call_id, "Hello, this is HeartKart calling. Thank you!")
    
    # Create TwiML response
    response = VoiceResponse()
    
    # Say the script with AI voice
    response.say(
        script,
        voice='Polly.Joanna',  # Amazon Polly voice
        language='en-US'
    )
    
    # Optionally gather response
    gather = Gather(
        input='speech',
        action=f'/api/vendor/response/{call_id}',
        method='POST',
        speech_timeout='auto',
        timeout=5
    )
    gather.say(
        "Please respond after the beep.",
        voice='Polly.Joanna'
    )
    response.append(gather)
    
    # If no response, say goodbye
    response.say(
        "Thank you for your time. We'll send a confirmation email. Goodbye!",
        voice='Polly.Joanna'
    )
    
    return Response(str(response), mimetype='text/xml')


@app.route('/api/vendor/response/<call_id>', methods=['POST'])
def vendor_response(call_id):
    """Handle vendor's speech response"""
    from flask import Response
    from twilio.twiml.voice_response import VoiceResponse
    
    # Get speech transcription
    speech_result = request.form.get('SpeechResult', '')
    confidence = request.form.get('Confidence', '')
    
    print(f"📝 Vendor response for {call_id}: {speech_result} (confidence: {confidence})")
    
    # Log to DynamoDB (if available)
    # save_vendor_response(call_id, speech_result, confidence)
    
    # Respond
    response = VoiceResponse()
    response.say(
        "Thank you! We've recorded your response. We'll send a confirmation email shortly. Goodbye!",
        voice='Polly.Joanna'
    )
    
    return Response(str(response), mimetype='text/xml')


@app.route('/api/vendor/status/<call_id>', methods=['POST'])
def vendor_status(call_id):
    """Handle call status updates"""
    call_status = request.form.get('CallStatus', '')
    call_duration = request.form.get('CallDuration', '0')
    
    print(f"📞 Call {call_id} status: {call_status} (duration: {call_duration}s)")
    
    # Log to DynamoDB
    # update_call_status(call_id, call_status, call_duration)
    
    return jsonify({'status': 'success'})


@app.route('/api/vendor/recording/<call_id>', methods=['POST'])
def vendor_recording(call_id):
    """Handle call recording"""
    recording_url = request.form.get('RecordingUrl', '')
    recording_duration = request.form.get('RecordingDuration', '0')
    
    print(f"🎙️ Recording for {call_id}: {recording_url} ({recording_duration}s)")
    
    # Save recording URL to DynamoDB
    # save_recording(call_id, recording_url, recording_duration)
    
    return jsonify({'status': 'success'})


@app.route('/api/vendor/call/test', methods=['POST'])
def test_vendor_call():
    """Test endpoint to initiate a vendor call"""
    try:
        data = request.get_json()
        phone_number = data.get('phone_number')
        script = data.get('script', 'Hello, this is a test call from HeartKart.')
        
        if not phone_number:
            return jsonify({'status': 'error', 'error': 'phone_number required'}), 400
        
        # Import here to avoid circular dependency
        sys.path.append(os.path.join(os.path.dirname(__file__), 'agents', 'vendor_caller'))
        from vendor_caller_agent import initiate_call
        
        # Store script for TwiML endpoint
        import uuid
        call_id = f"CALL-{uuid.uuid4().hex[:12]}"
        call_scripts[call_id] = script
        
        # Initiate call
        context = {
            'vendor_name': 'Test Vendor',
            'contact_person': 'Test Contact',
            'order_details': 'Test order',
            'total_amount': 100.00,
            'delivery_date': 'as soon as possible'
        }
        
        result = initiate_call(
            vendor_name='Test Vendor',
            call_type='place_order',
            context=context,
            phone_number=phone_number
        )
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ============================================================================
# INVENTORY ENDPOINTS
# ============================================================================

@app.route('/api/inventory', methods=['GET'])
def get_inventory():
    """Get all inventory items from DynamoDB"""
    try:
        # Import product data access layer
        sys.path.insert(0, os.path.dirname(__file__))
        from product_data_access import get_inventory_for_frontend
        
        # Get inventory from DynamoDB
        result = get_inventory_for_frontend(limit=10000)
        return jsonify(result)
        
    except Exception as e:
        print(f"Error fetching inventory: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'services': {
            'replenishment_planner': 'active',
            'stockout_sentinel': 'active',
            'inventory_copilot': 'active'
        }
    })


@app.route('/api/call-vendor', methods=['POST'])
@app.route('/api/call-vendor-v2', methods=['POST'])
def call_vendor():
    """Make AI call to vendor using Nova Sonic with automatic vendor fallback"""
    try:
        data = request.json
        from twilio.rest import Client
        
        # Get Twilio credentials
        TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
        TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
        TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
        
        # Get ngrok URL from environment or use default
        NGROK_URL = os.getenv('NGROK_URL', 'https://precompliant-cason-unencroached.ngrok-free.dev')
        
        # Create WebSocket URL for Nova Sonic
        websocket_url = f"wss://{NGROK_URL.replace('https://', '').replace('http://', '')}/media-stream"
        
        # Create TwiML that connects to Nova Sonic WebSocket
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{websocket_url}" />
    </Connect>
</Response>"""
        
        # Initiate call with Twilio
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        call = client.calls.create(
            twiml=twiml,
            to=data['vendor_phone'],
            from_=TWILIO_PHONE_NUMBER,
            record=True
        )
        
        # Store call context for Nova Sonic to use
        call_context = {
            'call_id': call.sid,
            'vendor_name': data.get('vendor_name', 'the vendor'),
            'contact_person': data.get('contact_person', 'there'),
            'product_name': data.get('product_name', 'products'),
            'quantity': data.get('quantity', 0),
            'po_number': data.get('po_number', 'N/A'),
            'items': data.get('items', []),
            'total_amount': data.get('total_amount', 0),
            'delivery_date': data.get('delivery_date', 'as soon as possible')
        }
        
        # Create an order chain to track vendor fallback attempts
        import uuid as _uuid
        order_id = f"ORD-{_uuid.uuid4().hex[:12]}"
        order_chains[order_id] = {
            'order_details': {
                'product_name': data.get('product_name', 'products'),
                'category': data.get('category', ''),
                'sku': data.get('sku', ''),
                'items': data.get('items', []),
                'quantity': data.get('quantity', 0),
                'po_number': data.get('po_number', 'N/A'),
                'total_amount': data.get('total_amount', 0),
                'delivery_date': data.get('delivery_date', 'as soon as possible'),
            },
            'category': data.get('category', ''),
            'vendors_tried': [data.get('vendor_name', 'Vendor')],
            'attempt_number': 1,
            'max_attempts': 2,
            'current_call_sid': call.sid,
        }
        
        # Store metadata for call logs
        call_metadata_store[call.sid] = {
            'vendor_name': data.get('vendor_name', 'Vendor'),
            'product_name': data.get('product_name'),
            'quantity': data.get('quantity'),
            'po_number': data.get('po_number'),
            'order_id': order_id,
        }
        
        # Store full context so Nova Sonic WebSocket can fetch it by call SID
        call_metadata_store[call.sid].update(call_context)
        
        print(f"📋 Order chain created: {order_id} (vendor 1: {data.get('vendor_name')})")
        
        # Return call info
        return jsonify({
            'success': True,
            'call_sid': call.sid,
            'order_id': order_id,
            'status': 'initiated',
            'final_status': 'initiated',
            'message': 'Nova Sonic AI call initiated successfully',
            'websocket_url': websocket_url,
            'call_context': call_context
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@app.route('/api/get-call-status/<call_sid>', methods=['GET'])
def get_call_status(call_sid):
    """Get call status"""
    try:
        from twilio.rest import Client
        client = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
        call = client.calls(call_sid).fetch()
        recordings = client.recordings.list(call_sid=call_sid, limit=1)
        recording_url = f"https://api.twilio.com{recordings[0].uri.replace('.json', '.mp3')}" if recordings else None
        return jsonify({'success': True, 'status': call.status, 'duration': call.duration, 'recording_url': recording_url})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/get-call-metadata/<call_sid>', methods=['GET'])
def get_call_metadata(call_sid):
    """Return stored call context so Nova Sonic WebSocket server can read it"""
    meta = call_metadata_store.get(call_sid)
    if meta:
        return jsonify({'success': True, **meta})
    return jsonify({'success': False, 'error': 'Call metadata not found'}), 404


@app.route('/api/store-transcript', methods=['POST'])
def store_transcript():
    """Store call transcript from WebSocket server and trigger vendor fallback if needed"""
    try:
        data = request.json
        call_sid = data.get('call_sid')
        transcript = data.get('transcript')
        conversation_history = data.get('conversation_history', [])
        decision = data.get('decision', 'UNKNOWN')  # YES / NO / UNKNOWN
        
        if call_sid:
            # Format transcript from conversation history
            formatted_transcript = []
            if conversation_history:
                for msg in conversation_history:
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')
                    
                    # Handle different content formats
                    if isinstance(content, list):
                        # Nova Sonic format: [{'text': '...'}]
                        text = content[0].get('text', '') if content else ''
                    elif isinstance(content, str):
                        text = content
                    else:
                        text = str(content)
                    
                    # Format role labels
                    if role == 'assistant':
                        role_label = "🤖 AI"
                    elif role == 'user':
                        role_label = "👤 Vendor"
                    else:
                        role_label = f"👤 {role.title()}"
                    
                    if text:
                        formatted_transcript.append(f"{role_label}: {text}")
            
            # Join formatted transcript
            transcript_text = '\n'.join(formatted_transcript) if formatted_transcript else ''
            
            # Store transcript
            call_transcripts_store[call_sid] = {
                'transcript': transcript_text,
                'conversation_history': conversation_history,
                'decision': decision,
                'stored_at': datetime.now().isoformat()
            }
            
            print(f"✅ Stored transcript for call {call_sid} ({len(transcript_text)} chars)")
            print(f"   Decision: {decision}")
            print(f"   Transcript preview: {transcript_text[:100]}...")
            
            # ================================================================
            # VENDOR FALLBACK: If vendor said NO, create rejection
            # notification and try the next vendor
            # ================================================================
            fallback_initiated = False
            if decision == 'NO':
                # Find the order chain for this call
                meta = call_metadata_store.get(call_sid, {})
                order_id = meta.get('order_id')
                vendor_name = meta.get('vendor_name', 'Unknown')
                product_name = meta.get('product_name', 'Product')

                # Extract rejection reason from transcript
                rejection_reason = _extract_rejection_reason(transcript_text)

                # Create rejection notification (no PO, no email)
                rejection_notif = {
                    'id': f"notif-reject-{call_sid[:8]}",
                    'type': 'vendor_call_rejection',
                    'timestamp': datetime.now().isoformat(),
                    'title': f"Vendor Rejected: {vendor_name}",
                    'message': f"{vendor_name} rejected the order for {product_name}. Reason: {rejection_reason}",
                    'po_number': 'N/A',
                    'vendor_name': vendor_name,
                    'product_name': product_name,
                    'call_sid': call_sid,
                    'call_duration': 0,
                    'subject': f"Vendor Rejected: {vendor_name} - {rejection_reason}",
                    'body': (
                        f"Vendor {vendor_name} was contacted for {product_name} "
                        f"but declined the order.\n\n"
                        f"Rejection reason: {rejection_reason}\n\n"
                        f"The system is automatically contacting the next available vendor."
                    ),
                    'pdf_url': '',
                    'created_at': datetime.now().isoformat(),
                    'status': 'failed',
                    'order_status': 'rejected',
                    'rejection_reason': rejection_reason,
                    'priority': 'high',
                    'actions': [{'label': 'View Call Log', 'action': 'view_call_logs'}],
                    'metadata': {
                        'call_transcript': transcript_text,
                    }
                }
                notifications_store[call_sid] = rejection_notif
                print(f"   🔔 Rejection notification created for {vendor_name}: {rejection_reason}")

                if order_id and order_id in order_chains:
                    chain = order_chains[order_id]
                    print(f"\n🔄 Vendor '{vendor_name}' declined order {order_id}")
                    print(f"   Attempt {chain['attempt_number']} of {chain['max_attempts']}")

                    if chain['attempt_number'] < chain['max_attempts']:
                        print(f"   ➡️  Initiating fallback call to next vendor...")
                        _initiate_fallback_call(order_id)
                        fallback_initiated = True
                    else:
                        print(f"   ⏹️  All {chain['max_attempts']} vendors tried. Order {order_id} could not be placed.")
                else:
                    print(f"   ⚠️  No order chain found for call {call_sid} — cannot trigger fallback")
            
            return jsonify({
                'success': True,
                'transcript_length': len(transcript_text),
                'decision': decision,
                'fallback_initiated': fallback_initiated,
            })
        
        return jsonify({'success': False, 'error': 'Missing call_sid'}), 400
        
    except Exception as e:
        print(f"Error storing transcript: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/get-transcript/<call_sid>', methods=['GET'])
def get_transcript(call_sid):
    """Get transcript for a specific call, including notification if available"""
    try:
        stored = call_transcripts_store.get(call_sid, {})
        transcript = stored.get('transcript', '')
        decision = stored.get('decision')

        if not transcript:
            return jsonify({
                'success': False,
                'call_sid': call_sid,
                'transcript': None,
                'message': 'Transcript not available yet'
            })

        # Build notification based on decision
        notification = notifications_store.get(call_sid)

        if not notification and decision and decision != 'PENDING':
            meta = call_metadata_store.get(call_sid, {})
            vendor_name = meta.get('vendor_name', 'Vendor')
            product_name = meta.get('product_name', 'Product')
            contact_person = meta.get('contact_person', 'there')
            po_number = meta.get('po_number', f"PO-{call_sid[:8]}")
            items = meta.get('items', [])
            total_amount = meta.get('total_amount', 0)
            delivery_date = meta.get('delivery_date', 'as soon as possible')

            if decision == 'YES':
                # Generate PO PDF
                pdf_url = ''
                try:
                    from agents.vendor_caller.po_pdf_generator import generate_vendor_po_pdf
                    po_data = {
                        'po_number': po_number,
                        'vendor': {'name': vendor_name, 'phone': '', 'email': '', 'address': 'TBD'},
                        'buyer': {'company': 'HeartKart', 'contact': 'Sarah Johnson',
                                  'email': 'procurement@heartkart.com', 'phone': '+1-555-0100'},
                        'items': items,
                        'total_amount': total_amount,
                        'delivery_date': delivery_date,
                        'date': datetime.now().isoformat(),
                        'payment_terms': 'Net 30',
                        'shipping_method': 'Standard Ground',
                    }
                    pdf_bytes = generate_vendor_po_pdf(po_data)
                    pdf_dir = os.path.join(os.path.dirname(__file__), 'generated_pos')
                    os.makedirs(pdf_dir, exist_ok=True)
                    pdf_path = os.path.join(pdf_dir, f"{po_number}.pdf")
                    with open(pdf_path, 'wb') as f:
                        f.write(pdf_bytes)
                    api_url = os.getenv('API_URL', 'http://localhost:5000')
                    pdf_url = f"{api_url.rstrip('/')}/api/po-pdfs/{po_number}.pdf"
                except Exception as pdf_err:
                    print(f"Warning: PO PDF generation failed: {pdf_err}")

                today_str = datetime.now().strftime('%B %d, %Y')
                items_lines = ''
                for i, item in enumerate(items, 1):
                    item_name = item.get('name', 'Item')
                    item_qty = item.get('quantity', 0)
                    items_lines += f"    {i}. {item_name} - Qty: {item_qty}\n"
                if not items_lines:
                    items_lines = f"    1. {product_name}\n"

                notification = {
                    'id': f"notif-{call_sid}",
                    'po_number': po_number,
                    'vendor_name': vendor_name,
                    'call_sid': call_sid,
                    'call_duration': 0,
                    'subject': f"Purchase Order {po_number} - Confirmation | HeartKart",
                    'body': (
                        f"Dear {contact_person},\n\n"
                        f"Thank you for confirming the order. Please find the details below:\n\n"
                        f"PO Number: {po_number}\n"
                        f"Order Date: {today_str}\n"
                        f"Delivery Date: {delivery_date}\n\n"
                        f"Items:\n{items_lines}\n"
                        f"Total: Rs. {total_amount}\n\n"
                        f"Best regards,\nHeartKart Procurement Team"
                    ),
                    'pdf_url': pdf_url,
                    'created_at': datetime.now().isoformat(),
                    'status': 'pending',
                    'type': 'vendor_call_success',
                    'order_status': 'pending_email',
                    'product_name': product_name,
                    'metadata': {
                        'contact_person': contact_person,
                        'delivery_date': delivery_date,
                        'total_amount': total_amount,
                        'items': items,
                        'call_transcript': transcript,
                    },
                }
                notifications_store[call_sid] = notification
            else:
                # NO or UNKNOWN — rejection notification (no PO, no email)
                rejection_reason = _extract_rejection_reason(transcript)
                notification = {
                    'id': f"notif-reject-{call_sid[:8]}",
                    'type': 'vendor_call_rejection',
                    'timestamp': datetime.now().isoformat(),
                    'title': f"Vendor Rejected: {vendor_name}",
                    'message': f"{vendor_name} rejected the order. Reason: {rejection_reason}",
                    'po_number': 'N/A',
                    'vendor_name': vendor_name,
                    'product_name': product_name,
                    'call_sid': call_sid,
                    'call_duration': 0,
                    'subject': f"Vendor Rejected: {vendor_name} - {rejection_reason}",
                    'body': (
                        f"Vendor {vendor_name} was contacted for {product_name} "
                        f"but declined the order.\n\n"
                        f"Rejection reason: {rejection_reason}\n\n"
                        f"The system is automatically contacting the next available vendor."
                    ),
                    'pdf_url': '',
                    'created_at': datetime.now().isoformat(),
                    'status': 'failed',
                    'order_status': 'rejected',
                    'rejection_reason': rejection_reason,
                    'priority': 'high',
                    'actions': [{'label': 'View Call Log', 'action': 'view_call_logs'}],
                    'metadata': {'call_transcript': transcript},
                }
                notifications_store[call_sid] = notification

        return jsonify({
            'success': True,
            'call_sid': call_sid,
            'transcript': transcript,
            'decision': decision,
            'notification': notification,
            'stored_at': stored.get('stored_at')
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/call-logs', methods=['GET'])
def get_call_logs():
    """Get all call logs with transcripts"""
    try:
        from twilio.rest import Client
        client = Client(os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
        
        # Fetch recent calls (last 50)
        calls = client.calls.list(limit=50)
        
        call_logs = []
        for call in calls:
            # Get recordings for this call
            recordings = client.recordings.list(call_sid=call.sid, limit=1)
            recording_url = f"https://api.twilio.com{recordings[0].uri.replace('.json', '.mp3')}" if recordings else None
            
            # Get stored metadata for this call
            metadata = call_metadata_store.get(call.sid, {})
            
            # Get stored transcript (from WebSocket server) - DO NOT use Twilio transcripts
            stored_transcript = call_transcripts_store.get(call.sid, {})
            final_transcript = stored_transcript.get('transcript') or None
            
            call_logs.append({
                'call_sid': call.sid,
                'vendor_name': metadata.get('vendor_name', 'Vendor'),
                'vendor_phone': call.to,
                'status': call.status,
                'duration': call.duration or 0,
                'started_at': call.start_time.isoformat() if call.start_time else None,
                'ended_at': call.end_time.isoformat() if call.end_time else None,
                'transcript': final_transcript,
                'recording_url': recording_url,
                'product_name': metadata.get('product_name'),
                'quantity': metadata.get('quantity'),
                'po_number': metadata.get('po_number')
            })
        
        return jsonify({'success': True, 'calls': call_logs})
    except Exception as e:
        import traceback
        return jsonify({'success': False, 'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/draft-email', methods=['POST'])
def draft_email_endpoint():
    """Draft email"""
    try:
        data = request.json
        import sys
        sys.path.insert(0, 'agents/email_drafter')
        from email_drafter_agent import EmailDrafterAgent
        email_drafter = EmailDrafterAgent()
        draft_email = email_drafter.draft_po_email(
            vendor_name=data['vendor_name'], contact_person=data['contact_person'],
            po_number=data['po_number'], items=data['items'], total_amount=data['total_amount'],
            delivery_date=data['delivery_date'], call_transcript=data.get('call_transcript'),
            call_summary=data.get('call_summary')
        )
        return jsonify({'success': True, 'email': draft_email})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# MARKET INTELLIGENCE ENDPOINTS
# ============================================================================

@app.route('/api/market-intelligence', methods=['GET', 'POST'])
def get_market_intelligence():
    """Get market intelligence report (powered by local Strands agent)"""
    try:
        # Get query parameters
        if request.method == 'POST':
            data = request.json or {}
        else:
            data = request.args.to_dict()

        query = data.get('query')
        category = data.get('category')
        region = data.get('region')
        report_type = data.get('report_type', 'full')

        # Generate report based on type
        if report_type == 'competitor':
            result = _mi_competitor_price_index(category)
            return jsonify({'success': True, 'report_type': 'competitor', 'data': result})

        if report_type == 'regional':
            result = _mi_regional_demand_trends(region)
            return jsonify({'success': True, 'report_type': 'regional', 'data': result})

        if report_type == 'category':
            result = _mi_category_trend_signals()
            return jsonify({'success': True, 'report_type': 'category', 'data': result})

        # full report
        result = _mi_generate_report(query, category, region)
        return jsonify({
            'success': result.get('status') == 'success',
            'report_type': 'full',
            'data': result
        })

    except Exception as e:
        print(f"Error getting market intelligence: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# PRICING INTELLIGENCE ENDPOINTS
# ============================================================================

@app.route('/api/pricing-intelligence', methods=['GET', 'POST'])
def get_pricing_intelligence():
    """Get pricing intelligence report (powered by local Strands agent)"""
    try:
        # Get query parameters
        if request.method == 'POST':
            data = request.json or {}
        else:
            data = request.args.to_dict()
        
        query = data.get('query')
        sku = data.get('sku')
        category = data.get('category')
        analysis_type = data.get('analysis_type', 'full')
        force_refresh = data.get('_t') is not None  # If timestamp parameter exists, force refresh
        
        # Cache + timeout controls (demo/dev)
        cache_ttl = int(os.getenv("PRICING_CACHE_TTL_SECONDS", "60"))
        timeout_seconds = int(os.getenv("PRICING_TIMEOUT_SECONDS", "60"))
        cache_key = f"{analysis_type}::{sku or ''}::{category or ''}::{query or ''}"

        # Only use cache if not forcing refresh
        cached = None
        if not force_refresh:
            cached = _cache_get(_pricing_cache, cache_key, ttl_seconds=cache_ttl)
        
        if cached is not None:
            return jsonify({
                'success': True,
                'analysis_type': analysis_type,
                'data': cached,
                'cached': True,
            })
        
        # Always generate a consistent, panel-friendly payload shape (even for
        # optimization/price_range/etc). We also enforce a timeout for ALL
        # analysis types so the UI never hangs.
        ok, value = _run_with_timeout(
            lambda: _pi_generate_report(query, sku, category, analysis_type),
            timeout_seconds=timeout_seconds,
        )
        if ok and isinstance(value, dict):
            _cache_set(_pricing_cache, cache_key, value)
            return jsonify({
                'success': value.get('status') == 'success',
                'analysis_type': analysis_type,
                'data': value,
            })

        # Timed out or failed: return fast fallback
        fallback = _pricing_fallback_payload(analysis_type=analysis_type, sku=sku, category=category)
        _cache_set(_pricing_cache, cache_key, fallback)
        return jsonify({
            'success': True,
            'analysis_type': analysis_type,
            'data': fallback,
            'fallback': True,
        })
        
    except Exception as e:
        print(f"Error getting pricing intelligence: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


if __name__ == '__main__':
    print("=" * 70)
    print("🎄 HeartKart Inventory Management API")
    print("=" * 70)
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
    print("\n🏷️  Markdown & Clearance Coach Endpoints:")
    print("  GET  /api/markdown/report")
    print("  GET  /api/markdown/aged-inventory")
    print("  GET  /api/markdown/timeline")
    print("  GET  /api/markdown/bundles")
    print("  GET  /api/markdown/summary")
    print("\n📦 Inventory Endpoints:")
    print("  GET  /api/inventory")
    print("\n🏥 Health Check:")
    print("  GET  /api/health")
    print("\n📞 Vendor Calling Endpoints:")
    print("  POST /api/call-vendor")
    print("  GET  /api/get-call-status/<call_sid>")
    print("  POST /api/draft-email")
    print("\n🌐 Running on http://localhost:5000")
    print("=" * 70)
    
    # Default to non-reloading server for demo stability; enable with FLASK_DEBUG=1
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=os.getenv('FLASK_DEBUG') == '1',
        threaded=True,
    )
