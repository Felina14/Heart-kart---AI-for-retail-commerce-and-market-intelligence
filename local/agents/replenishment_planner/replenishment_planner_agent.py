#!/usr/bin/env python3
"""
Replenishment Planner Agent
Uses Amazon Nova to analyze inventory and recommend reorders
"""

import boto3
import json
import os
import sys
import threading
from datetime import datetime, timedelta
from typing import List, Dict
from decimal import Decimal
from collections import defaultdict

# Initialize AWS clients
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# Import product data access layer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from product_data_access import (
    get_all_products,
    get_low_stock_products as get_low_stock_from_db,
    get_product_by_sku,
)


def get_low_stock_products(threshold: int = 20) -> List[Dict]:
    """Get products below reorder threshold from DynamoDB."""
    try:
        scan_limit = int(os.getenv("REPLENISHMENT_SCAN_LIMIT", "1500"))
        take_limit = int(os.getenv("REPLENISHMENT_TAKE_LIMIT", "100"))

        all_products = get_all_products(limit=scan_limit)
        filtered = []
        for p in all_products:
            stock_qty = int(p.get('stock_quantity', p.get('inventory', 0)) or 0)
            rop = int(p.get('reorder_point', 10) or 10)
            cutoff = threshold if threshold is not None else rop
            if stock_qty < cutoff:
                filtered.append(p)

        filtered.sort(key=lambda x: int(x.get('stock_quantity', x.get('inventory', 0)) or 0))
        products = filtered[:take_limit]

        formatted = []
        for product in products:
            formatted.append({
                'sku': product.get('sku', 'N/A'),
                'name': product.get('name', 'Unknown'),
                'category': product.get('category', 'Uncategorized'),
                'stock_quantity': int(product.get('stock_quantity', 0)),
                'price': float(product.get('price', 0)),
                'popularity': product.get('rating', 50),
                'vendor': product.get('vendor_name', 'General Gift Wholesale'),
                'lead_time_days': int(product.get('vendor_lead_time_days', product.get('lead_time_days', 7)) or 7),
                'moq': int(product.get('vendor_moq', 50) or 50),
                'vendor_on_time_rate': float(product.get('vendor_on_time_rate', 0.90) or 0.90),
                'sales_velocity': float(product.get('sales_velocity', 0.5) or 0.5),
            })
        
        return formatted
    except Exception as e:
        print(f"Error fetching low stock products: {e}")
        return []


def calculate_sales_velocity(sku: str, days: int = 30) -> float:
    """Return sales_velocity stored on the product record."""
    try:
        product = get_product_by_sku(sku)
        if product:
            v = product.get('sales_velocity') or product.get('velocity')
            if v is not None:
                try:
                    v_float = float(v)
                    if v_float > 0:
                        return round(v_float, 2)
                except Exception:
                    pass
        return 0.5
    except Exception:
        return 0.5


def calculate_reorder_point(velocity: float, lead_time_days: int = 7, safety_stock_days: int = 3) -> int:
    """
    Calculate Reorder Point (ROP)
    ROP = (Average Daily Sales × Lead Time) + Safety Stock
    """
    rop = (velocity * lead_time_days) + (velocity * safety_stock_days)
    return max(int(rop), 10)


def calculate_order_quantity(velocity: float, current_stock: int, rop: int, moq: int = 50) -> int:
    """
    Calculate Economic Order Quantity (EOQ) simplified
    Ensures we order enough to last 30-60 days
    """
    target_stock = int(velocity * 45)
    order_qty = max(target_stock - current_stock, moq)
    if order_qty % moq != 0:
        order_qty = ((order_qty // moq) + 1) * moq
    return order_qty


def get_vendor_info_from_db(sku: str) -> Dict:
    """Get vendor information from DynamoDB Products table."""
    try:
        product = get_product_by_sku(sku)
        if product:
            return {
                'vendor': product.get('vendor_name', 'General Gift Wholesale'),
                'lead_time': int(product.get('vendor_lead_time_days', product.get('lead_time_days', 7)) or 7),
                'moq': int(product.get('vendor_moq', 50) or 50),
                'on_time_rate': float(product.get('vendor_on_time_rate', 0.90) or 0.90)
            }
    except Exception as e:
        print(f"Error fetching vendor info for {sku}: {e}")
    
    return {'vendor': 'General Gift Wholesale', 'lead_time': 7, 'moq': 50, 'on_time_rate': 0.90}


def analyze_with_nova(product_data: List[Dict]) -> str:
    """
    Use Amazon Nova to provide business reasoning on the replenishment situation.
    """
    # Build aggregated context — give Nova numbers to reason about, not raw lists
    total_products = len(product_data)
    critical = [p for p in product_data if p['urgency'] == 'CRITICAL']
    high     = [p for p in product_data if p['urgency'] == 'HIGH']
    medium   = [p for p in product_data if p['urgency'] == 'MEDIUM']
    low      = [p for p in product_data if p['urgency'] == 'LOW']

    # Category breakdown
    by_category = defaultdict(list)
    for p in product_data:
        by_category[p['category']].append(p)

    category_summary = {
        cat: {
            'count': len(items),
            'avg_days_to_stockout': round(sum(i['days_until_stockout'] for i in items) / len(items), 1),
            'total_reorder_cost': round(sum(i['estimated_cost'] for i in items), 2),
            'fastest_selling': min(items, key=lambda x: x['days_until_stockout'])['name']
        }
        for cat, items in by_category.items()
    }

    # Vendor risk
    by_vendor = defaultdict(list)
    for p in product_data:
        by_vendor[p['vendor']].append(p)
    vendor_summary = {
        v: {
            'products_at_risk': len(items),
            'avg_lead_time': round(sum(i['lead_time_days'] for i in items) / len(items), 1),
            'on_time_rate': items[0]['vendor_on_time_rate']
        }
        for v, items in by_vendor.items()
    }

    total_cost   = sum(p['estimated_cost'] for p in product_data)
    avg_velocity = round(sum(p['sales_velocity'] for p in product_data) / total_products, 2) if total_products else 0
    top_critical = sorted(critical, key=lambda x: x['days_until_stockout'])[:3]

    context = {
        'snapshot': {
            'total_low_stock_products': total_products,
            'critical_count': len(critical),
            'high_count': len(high),
            'medium_count': len(medium),
            'low_count': len(low),
            'total_reorder_investment_needed': round(total_cost, 2),
            'avg_sales_velocity_across_all': avg_velocity,
            'most_urgent_products': [
                {
                    'name': p['name'],
                    'category': p['category'],
                    'stock': p['current_stock'],
                    'days_left': p['days_until_stockout'],
                    'velocity': p['sales_velocity'],
                    'vendor': p['vendor'],
                    'lead_time': p['lead_time_days'],
                    'reorder_cost': p['estimated_cost']
                }
                for p in top_critical
            ]
        },
        'category_breakdown': category_summary,
        'vendor_risk': vendor_summary
    }
    
    prompt = f"""You are a senior supply chain analyst. You have just completed a replenishment analysis for HeartKart, a Valentine's Day products retailer.

Here is the data summary — do NOT repeat or list these back. Use them to REASON and EXPLAIN:

{json.dumps(context, indent=2)}

Write a flowing business analysis in 4 clearly labelled sections. Each section must contain paragraphs of reasoning, not bullet lists of products.

### Situation Overview
In 2-3 sentences: what is the overall health of the inventory right now? Reference the numbers (how many critical, total investment needed, which categories are most affected) and explain what this pattern suggests about the business.

### Root Cause & Category Insights
Which product categories are driving the most risk and why? Are there patterns — e.g. fast-moving low-cost items depleting faster than high-value ones? Is the velocity aligned with reorder points? What does the category distribution tell us about buying habits or forecasting gaps?

### Vendor & Supply Chain Risk
Based on lead times and on-time rates across vendors, where is the supply chain most exposed? If the most critical products have long lead times or unreliable vendors, explain that risk and its consequence. Which vendor relationship needs the most attention right now?

### Strategic Recommendation
What should the business do in the next 48 hours, this week, and this month? Think about cash flow (total investment required), which orders are truly time-sensitive vs. manageable, and how to prevent this situation from recurring. Suggest one structural improvement (e.g. reorder point calibration, safety stock policy, vendor diversification).

Write in a professional but direct tone. No product lists. No SKUs. Pure business reasoning."""

    try:
        response = bedrock.invoke_model(
            modelId='us.amazon.nova-lite-v1:0',
            body=json.dumps({
                'messages': [{'role': 'user', 'content': [{'text': prompt}]}],
                'inferenceConfig': {
                    'temperature': 0.6,
                    'maxTokens': 3000
                }
            })
        )
        result = json.loads(response['body'].read())
        return result['output']['message']['content'][0]['text']
        
    except Exception as e:
        print(f"Error calling Nova: {e}")
        return "Error: Could not get AI analysis"


def _run_with_timeout(fn, timeout_seconds: int, fallback):
    """Run a function with a timeout. If it doesn't finish, return fallback."""
    result = {"value": fallback}

    def _target():
        try:
            result["value"] = fn()
        except Exception as e:
            result["value"] = f"AI analysis unavailable: {e}"

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout_seconds)
    return result["value"]


def generate_replenishment_plan(threshold: int = 20, include_ai: bool = True) -> Dict:
    """
    Main function: Generate complete replenishment plan
    """
    print("🔍 Analyzing inventory levels...")
    
    # Get low stock products
    low_stock = get_low_stock_products(threshold=threshold)
    
    if not low_stock:
        return {
            'status': 'success',
            'message': 'All products are well-stocked!',
            'recommendations': []
        }
    
    print(f"📊 Found {len(low_stock)} products below reorder threshold")
    
    # Analyze each product
    recommendations = []
    
    for product in low_stock:
        sku = product['sku']
        current_stock = product['stock_quantity']
        category = product['category']
        
        velocity = float(product.get('sales_velocity') or 0.5)
        lead_time = int(product.get('lead_time_days') or 7)
        moq = int(product.get('moq') or 50)
        vendor_name = product.get('vendor') or 'General Gift Wholesale'
        vendor_on_time_rate = float(product.get('vendor_on_time_rate') or 0.90)
        
        rop = calculate_reorder_point(velocity, lead_time)
        order_qty = calculate_order_quantity(velocity, current_stock, rop, moq)
        
        days_until_stockout = int(current_stock / velocity) if velocity > 0 else 999
        stockout_date = (datetime.now() + timedelta(days=days_until_stockout)).strftime('%Y-%m-%d')
        
        if days_until_stockout <= 3:
            urgency = 'CRITICAL'
        elif days_until_stockout <= 7:
            urgency = 'HIGH'
        elif days_until_stockout <= 14:
            urgency = 'MEDIUM'
        else:
            urgency = 'LOW'
        
        recommendation = {
            'sku': sku,
            'name': product['name'],
            'category': category,
            'current_stock': current_stock,
            'reorder_point': rop,
            'sales_velocity': velocity,
            'days_until_stockout': days_until_stockout,
            'predicted_stockout_date': stockout_date,
            'urgency': urgency,
            'recommended_order_qty': order_qty,
            'vendor': vendor_name,
            'lead_time_days': lead_time,
            'moq': moq,
            'vendor_on_time_rate': f"{vendor_on_time_rate*100:.0f}%",
            'estimated_cost': round(product['price'] * order_qty, 2),
            'reason': f"Stock at {current_stock} units, selling {velocity:.1f}/day. Stockout risk in {days_until_stockout} days."
        }
        
        recommendations.append(recommendation)
    
    # Sort by urgency and stockout date
    urgency_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
    recommendations.sort(key=lambda x: (urgency_order[x['urgency']], x['days_until_stockout']))
    
    # Get AI analysis
    ai_analysis = None
    if include_ai:
        print("🤖 Getting AI recommendations from Amazon Nova...")
        ai_timeout = int(os.getenv("REPLENISHMENT_AI_TIMEOUT_SECONDS", "15"))
        ai_analysis = _run_with_timeout(
            lambda: analyze_with_nova(recommendations),
            timeout_seconds=ai_timeout,
            fallback="AI analysis timed out. Data-driven reorder recommendations are shown above.",
        )
    
    # Calculate totals
    total_cost = sum(r['estimated_cost'] for r in recommendations)
    critical_count = sum(1 for r in recommendations if r['urgency'] == 'CRITICAL')
    high_count = sum(1 for r in recommendations if r['urgency'] == 'HIGH')
    
    return {
        'status': 'success',
        'generated_at': datetime.now().isoformat(),
        'summary': {
            'total_products_needing_reorder': len(recommendations),
            'critical_urgency': critical_count,
            'high_urgency': high_count,
            'total_estimated_cost': total_cost,
            'average_days_until_stockout': round(sum(r['days_until_stockout'] for r in recommendations) / len(recommendations), 1)
        },
        'ai_analysis': ai_analysis,
        'recommendations': recommendations
    }


if __name__ == '__main__':
    print("=" * 70)
    print("🎄 REPLENISHMENT PLANNER - Powered by Amazon Nova")
    print("=" * 70)
    
    plan = generate_replenishment_plan()
    
    if plan['status'] == 'success':
        summary = plan.get('summary', {})
        
        print(f"\n📊 SUMMARY")
        print(f"  Products needing reorder: {summary.get('total_products_needing_reorder', 0)}")
        print(f"  Critical urgency: {summary.get('critical_urgency', 0)}")
        print(f"  High urgency: {summary.get('high_urgency', 0)}")
        print(f"  Total estimated cost: ${summary.get('total_estimated_cost', 0):,.2f}")
        
        print(f"\n🤖 AI ANALYSIS:")
        print(plan.get('ai_analysis', 'No analysis available'))
        
        print(f"\n📋 TOP 10 PRIORITY REORDERS:")
        print("-" * 70)
        
        for i, rec in enumerate(plan['recommendations'][:10], 1):
            print(f"\n{i}. {rec['name']} ({rec['sku']})")
            print(f"   Urgency: {rec['urgency']} | Stock: {rec['current_stock']} units")
            print(f"   Stockout in: {rec['days_until_stockout']} days ({rec['predicted_stockout_date']})")
            print(f"   Order: {rec['recommended_order_qty']} units from {rec['vendor']}")
            print(f"   Cost: ${rec['estimated_cost']:,.2f} | Lead time: {rec['lead_time_days']} days")
            print(f"   Reason: {rec['reason']}")
        
        with open('replenishment_plan.json', 'w') as f:
            json.dump(plan, f, indent=2, default=str)
        
        print(f"\n✅ Full plan saved to: replenishment_plan.json")
    
    print("\n" + "=" * 70)
