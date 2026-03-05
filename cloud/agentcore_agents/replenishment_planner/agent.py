"""
Replenishment Planner Agent for AWS Bedrock AgentCore Runtime (Strands Framework)

AI-powered inventory replenishment planning agent that analyzes stock levels,
sales velocity, and demand patterns to recommend optimal reorder quantities and timing.
Uses the Strands framework with @tool decorators for all data access operations.
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any

import boto3
from boto3.dynamodb.conditions import Attr
from strands import tool, Agent
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# Initialize AgentCore App
app = BedrockAgentCoreApp()

# Initialize AWS clients
REGION = os.environ.get('AWS_REGION', 'us-east-1')
dynamodb = boto3.resource('dynamodb', region_name=REGION)
sales_table = dynamodb.Table('SalesHistory')

# Import product data access layer (local copy for Docker container)
from product_data_access import get_all_products, get_product_by_sku


# ============================================================================
# HELPER FUNCTIONS (pure calculations, not tools)
# ============================================================================

def calculate_reorder_point(velocity: float, lead_time_days: int = 7, safety_stock_days: int = 3) -> int:
    """Calculate Reorder Point (ROP)"""
    rop = (velocity * lead_time_days) + (velocity * safety_stock_days)
    return max(int(rop), 10)


def calculate_order_quantity(velocity: float, current_stock: int, rop: int, moq: int = 50) -> int:
    """Calculate Economic Order Quantity (EOQ) simplified"""
    target_stock = int(velocity * 45)
    order_qty = max(target_stock - current_stock, moq)
    if order_qty % moq != 0:
        order_qty = ((order_qty // moq) + 1) * moq
    return order_qty


# ============================================================================
# STRANDS TOOLS
# ============================================================================

@tool
def get_low_stock_products(threshold: int = 20) -> List[Dict]:
    """
    Retrieve products with stock quantity at or below the threshold.

    Args:
        threshold: Maximum stock quantity to consider "low stock" (default: 20)

    Returns:
        List of low-stock product dicts with sku, name, category, price,
        stock_quantity, vendor_name, vendor_lead_time_days, vendor_moq.
    """
    try:
        all_products = get_all_products(limit=1000)
        low_stock = []
        for product in all_products:
            stock = int(product.get('stock_quantity', product.get('inventory', 0)))
            if 0 < stock <= threshold:
                low_stock.append({
                    'sku': product.get('sku', ''),
                    'name': product.get('name', ''),
                    'category': product.get('category', ''),
                    'price': float(product.get('price', 0)),
                    'stock_quantity': stock,
                    'vendor_name': product.get('vendor_name', 'General Valentine Wholesale'),
                    'vendor_lead_time_days': int(product.get('vendor_lead_time_days', 7)),
                    'vendor_moq': int(product.get('vendor_moq', 50)),
                })
        low_stock.sort(key=lambda x: x['stock_quantity'])
        return low_stock[:100]
    except Exception as e:
        print(f"Error fetching low stock products: {e}")
        return []


@tool
def get_sales_velocity(sku: str, days: int = 30) -> float:
    """
    Calculate average daily sales velocity for a product.

    Args:
        sku: Product SKU identifier
        days: Historical window in days (default: 30)

    Returns:
        Average units sold per day as a float (minimum 0.5 when no data).
    """
    try:
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        response = sales_table.scan(
            FilterExpression=Attr('date').gte(cutoff_date) & Attr('sku').eq(sku)
        )
        records = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = sales_table.scan(
                FilterExpression=Attr('date').gte(cutoff_date) & Attr('sku').eq(sku),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            records.extend(response.get('Items', []))

        total_sold = sum(int(r.get('quantity', 0)) for r in records)

        velocity = total_sold / days if days > 0 else 0
        return round(velocity, 2) if velocity > 0 else 0.5
    except Exception as e:
        print(f"Error calculating sales velocity for {sku}: {e}")
        return 0.5


@tool
def get_vendor_info(sku: str) -> Dict:
    """
    Get vendor information for a product including lead time and MOQ.

    Args:
        sku: Product SKU identifier

    Returns:
        Dict with vendor (name), lead_time (days), moq (min order qty), on_time_rate (0-1).
    """
    try:
        product = get_product_by_sku(sku)
        if product:
            return {
                'vendor': product.get('vendor_name', 'General Valentine Wholesale'),
                'lead_time': int(product.get('vendor_lead_time_days', 7)),
                'moq': int(product.get('vendor_moq', 50)),
                'on_time_rate': float(product.get('vendor_on_time_rate', 0.90)),
            }
    except Exception as e:
        print(f"Error fetching vendor info for {sku}: {e}")
    return {
        'vendor': 'General Valentine Wholesale',
        'lead_time': 7,
        'moq': 50,
        'on_time_rate': 0.90,
    }


# ============================================================================
# STRANDS AGENT
# ============================================================================

bedrock_model = BedrockModel(
    model_id=os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
    temperature=float(os.getenv("MODEL_TEMPERATURE", "0.3")),
)

agent = Agent(
    model=bedrock_model,
    tools=[get_low_stock_products, get_sales_velocity, get_vendor_info],
    system_prompt=(
        "You are the HeartKart Replenishment Planner Agent. Analyze inventory levels "
        "and generate actionable replenishment recommendations for Valentine's Day products.\n\n"
        "Use your tools to:\n"
        "1. Find products with low stock using get_low_stock_products\n"
        "2. Assess sales velocity using get_sales_velocity\n"
        "3. Get vendor lead times and MOQ using get_vendor_info\n\n"
        "Deliver a prioritized replenishment plan with urgency levels (CRITICAL/HIGH/MEDIUM/LOW), "
        "recommended order quantities, risk assessment, and budget optimization. "
        "Focus on preventing Valentine's Day stockouts while managing cash flow."
    ),
)


# ============================================================================
# CORE PLAN BUILDER (structured output)
# ============================================================================

def generate_replenishment_plan() -> Dict:
    """Generate complete replenishment plan using tools and Strands agent for AI analysis."""
    print("🔍 Analyzing inventory levels...")

    low_stock = get_low_stock_products(20)

    if not low_stock:
        return {
            'status': 'success',
            'message': 'All products are well-stocked!',
            'recommendations': [],
        }

    print(f"📊 Found {len(low_stock)} products below reorder threshold")

    recommendations = []
    for product in low_stock:
        sku = product['sku']
        current_stock = product['stock_quantity']

        velocity = get_sales_velocity(sku, 30)
        vendor_info = get_vendor_info(sku)
        lead_time = vendor_info['lead_time']
        moq = vendor_info['moq']

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

        recommendations.append({
            'sku': sku,
            'name': product['name'],
            'category': product.get('category', ''),
            'current_stock': current_stock,
            'reorder_point': rop,
            'sales_velocity': velocity,
            'days_until_stockout': days_until_stockout,
            'predicted_stockout_date': stockout_date,
            'urgency': urgency,
            'recommended_order_qty': order_qty,
            'vendor': vendor_info['vendor'],
            'lead_time_days': lead_time,
            'moq': moq,
            'vendor_on_time_rate': f"{vendor_info['on_time_rate'] * 100:.0f}%",
            'estimated_cost': round(product['price'] * order_qty, 2),
            'reason': (
                f"Stock at {current_stock} units, selling {velocity:.1f}/day. "
                f"Stockout risk in {days_until_stockout} days."
            ),
        })

    urgency_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
    recommendations.sort(key=lambda x: (urgency_order[x['urgency']], x['days_until_stockout']))

    total_cost = sum(r['estimated_cost'] for r in recommendations)
    critical_count = sum(1 for r in recommendations if r['urgency'] == 'CRITICAL')
    high_count = sum(1 for r in recommendations if r['urgency'] == 'HIGH')
    medium_count = sum(1 for r in recommendations if r['urgency'] == 'MEDIUM')
    low_count = sum(1 for r in recommendations if r['urgency'] == 'LOW')

    # Build a concise summary for the AI (NOT raw product JSON)
    vendors_involved = {}
    categories_at_risk = set()
    for r in recommendations:
        v = r.get('vendor', 'Unknown')
        vendors_involved[v] = vendors_involved.get(v, 0) + 1
        categories_at_risk.add(r.get('category', 'General'))

    top_critical = [f"{r['name']} (stock {r.get('current_stock', '?')}, "
                    f"velocity {r.get('sales_velocity', '?')}/day, "
                    f"stockout in {r['days_until_stockout']}d)"
                    for r in recommendations[:5] if r['urgency'] == 'CRITICAL']

    analysis_prompt = (
        f"You are analyzing a Valentine's Day inventory replenishment plan. "
        f"DO NOT list individual products. Instead, provide strategic analysis.\n\n"
        f"DATA SUMMARY:\n"
        f"- Total products needing reorder: {len(recommendations)}\n"
        f"- CRITICAL: {critical_count}, HIGH: {high_count}, MEDIUM: {medium_count}, LOW: {low_count}\n"
        f"- Total estimated reorder cost: ₹{total_cost:,.0f}\n"
        f"- Vendors involved: {json.dumps(vendors_involved)}\n"
        f"- Product categories at risk: {', '.join(list(categories_at_risk)[:10])}\n"
        f"- Top critical items: {'; '.join(top_critical[:3]) if top_critical else 'None'}\n\n"
        f"Write your analysis using EXACTLY these 4 markdown sections. "
        f"Each section must have 3-5 bullet points. Be specific with numbers.\n\n"
        f"### Priority Ranking & Immediate Actions\n"
        f"(Which urgency tiers need attention first, what % of budget they represent, "
        f"key deadlines before Valentine's Day)\n\n"
        f"### Risk Assessment\n"
        f"(Stockout risk by category, vendor reliability concerns, "
        f"single-vendor dependency risks, lead time risks)\n\n"
        f"### Vendor Strategy\n"
        f"(Vendor concentration analysis, which vendors handle the most critical items, "
        f"negotiation leverage, diversification recommendations)\n\n"
        f"### Budget Optimization Advice\n"
        f"(How to phase spending, which orders to consolidate, "
        f"bulk discount opportunities, cash flow management tips)\n"
    )

    # Use Strands agent for AI analysis
    print("🤖 Getting AI recommendations from Strands agent...")
    try:
        agent_response = agent(analysis_prompt)
        ai_analysis = str(agent_response)
        # Strip <thinking> tags if present
        ai_analysis = re.sub(r'<thinking>.*?</thinking>', '', ai_analysis, flags=re.DOTALL).strip()
    except Exception as e:
        print(f"Error calling Strands agent: {e}")
        ai_analysis = (
            f"### Priority Ranking & Immediate Actions\n"
            f"- {critical_count} CRITICAL items need orders placed within 24 hours\n"
            f"- {high_count} HIGH urgency items should be ordered within 3-4 days\n"
            f"- Total reorder budget required: ₹{total_cost:,.0f}\n\n"
            f"### Risk Assessment\n"
            f"- {len(categories_at_risk)} product categories at risk of stockout before Valentine's Day\n"
            f"- {len(vendors_involved)} vendors involved — monitor lead times closely\n\n"
            f"### Vendor Strategy\n"
            f"- Consolidate orders per vendor to negotiate better terms\n"
            f"- Prioritize vendors with highest on-time delivery rates\n\n"
            f"### Budget Optimization Advice\n"
            f"- Phase CRITICAL orders first, then HIGH urgency within the week\n"
            f"- Total estimated cost: ₹{total_cost:,.0f} across {len(recommendations)} SKUs\n"
        )

    return {
        'status': 'success',
        'generated_at': datetime.now().isoformat(),
        'summary': {
            'total_products_needing_reorder': len(recommendations),
            'critical_urgency': critical_count,
            'high_urgency': high_count,
            'total_estimated_cost': total_cost,
            'average_days_until_stockout': round(
                sum(r['days_until_stockout'] for r in recommendations) / len(recommendations), 1
            ),
        },
        'ai_analysis': ai_analysis,
        'recommendations': recommendations,
    }


# ============================================================================
# AGENTCORE RUNTIME ENTRY POINT
# ============================================================================

@app.entrypoint
def replenishment_planner_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    AgentCore Runtime entry point for the Replenishment Planner Agent.

    Args:
        payload: Input containing optional action or request parameters

    Returns:
        Dictionary with replenishment recommendations
    """
    print(f"Received request: {json.dumps(payload, default=str)}")

    try:
        result = generate_replenishment_plan()
        print(
            f"Generated plan with "
            f"{result.get('summary', {}).get('total_products_needing_reorder', 0)} recommendations"
        )
        return result
    except Exception as e:
        import traceback
        print(f"Error in handler: {e}")
        traceback.print_exc()
        return {
            'status': 'error',
            'message': str(e),
            'traceback': traceback.format_exc(),
        }


if __name__ == "__main__":
    app.run()
