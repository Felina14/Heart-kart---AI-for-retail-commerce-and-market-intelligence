"""
Stockout Sentinel Agent for AWS Bedrock AgentCore Runtime (Strands Framework)

AI-powered stockout prediction and product substitute recommendation agent.
Analyzes inventory levels, sales velocity, and finds intelligent product alternatives.
Uses the Strands framework with @tool decorators for all data access operations.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any
from collections import defaultdict

import boto3
from strands import tool, Agent
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# Initialize AgentCore App
app = BedrockAgentCoreApp()

# Initialize AWS clients
REGION = os.environ.get('AWS_REGION', 'us-east-1')
dynamodb = boto3.resource('dynamodb', region_name=REGION)

# Import product data access layer (local copy for Docker container)
from product_data_access import get_all_products, get_product_by_sku, get_products_by_category


# ============================================================================
# HELPER FUNCTIONS (pure calculations, not tools)
# ============================================================================

def predict_stockout_date(current_stock: int, velocity: float) -> Dict:
    """Predict stockout risk level and date given current stock and velocity."""
    if velocity <= 0:
        return {'days_until_stockout': 999, 'stockout_date': None, 'risk_level': 'LOW'}

    days_until_stockout = int(current_stock / velocity)
    stockout_date = (datetime.now() + timedelta(days=days_until_stockout)).strftime('%Y-%m-%d')

    if days_until_stockout <= 3:
        risk_level = 'CRITICAL'
    elif days_until_stockout <= 7:
        risk_level = 'HIGH'
    elif days_until_stockout <= 14:
        risk_level = 'MEDIUM'
    else:
        risk_level = 'LOW'

    return {
        'days_until_stockout': days_until_stockout,
        'stockout_date': stockout_date,
        'risk_level': risk_level,
    }


# ============================================================================
# STRANDS TOOLS
# ============================================================================

@tool
def get_at_risk_inventory(stock_threshold: int = 30) -> List[Dict]:
    """
    Retrieve products at risk of stocking out within 14 days.

    Args:
        stock_threshold: Maximum stock quantity to consider "at risk" (default: 30)

    Returns:
        List of at-risk products with sku, name, category, price, current_stock,
        sales_velocity, days_until_stockout, stockout_date, risk_level.
    """
    try:
        all_products = get_all_products(limit=1000)
        at_risk = []

        for product in all_products:
            stock = int(product.get('stock_quantity', product.get('inventory', 0)))
            if stock <= 0 or stock > stock_threshold:
                continue

            velocity = float(product.get('sales_velocity', 0))
            if velocity <= 0:
                velocity = 0.5

            prediction = predict_stockout_date(stock, velocity)
            if prediction['days_until_stockout'] > 14:
                continue

            at_risk.append({
                'sku': product.get('sku', ''),
                'name': product.get('name', ''),
                'category': product.get('category', ''),
                'color': product.get('color', ''),
                'price': float(product.get('price', 0)),
                'current_stock': stock,
                'sales_velocity': velocity,
                'days_until_stockout': prediction['days_until_stockout'],
                'stockout_date': prediction['stockout_date'],
                'risk_level': prediction['risk_level'],
            })

        risk_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
        at_risk.sort(key=lambda x: (risk_order[x['risk_level']], x['days_until_stockout']))
        return at_risk[:100]

    except Exception as e:
        print(f"Error fetching at-risk inventory: {e}")
        return []


@tool
def find_product_substitutes(sku: str, max_substitutes: int = 5) -> List[Dict]:
    """
    Find substitute products for a given SKU based on category and price similarity.

    Args:
        sku: SKU of the product to find substitutes for
        max_substitutes: Maximum number of substitutes to return (default: 5)

    Returns:
        List of substitute products with sku, name, category, price, stock_quantity,
        match_score, and reason for the recommendation.
    """
    try:
        product = get_product_by_sku(sku)
        if not product:
            return []

        category = product.get('category', '')
        price = float(product.get('price', 0))
        color = product.get('color', '')

        min_price = price * 0.7
        max_price = price * 1.3

        candidates = get_products_by_category(category, limit=100)
        if not candidates:
            candidates = get_all_products(limit=1000)

        substitutes = []
        for candidate in candidates:
            cand_sku = candidate.get('sku', '')
            if cand_sku == sku:
                continue

            cand_stock = int(candidate.get('stock_quantity', candidate.get('inventory', 0)))
            if cand_stock <= 5:
                continue

            cand_price = float(candidate.get('price', 0))
            if not (min_price <= cand_price <= max_price):
                continue

            category_match = 1.0 if candidate.get('category') == category else 0.5
            color_match = 1.0 if candidate.get('color', '') == color else 0.3
            price_diff = abs(cand_price - price) / price if price > 0 else 0
            price_match = max(0, 1.0 - price_diff)

            overall_match = (category_match * 0.4 + color_match * 0.3 + price_match * 0.3) * 100

            reasons = []
            if category_match == 1.0:
                reasons.append(f"Same category ({candidate.get('category')})")
            if color_match == 1.0:
                reasons.append(f"Same color ({candidate.get('color', '')})")
            price_difference = cand_price - price
            if abs(price_difference) < 5:
                reasons.append("Similar price")
            elif price_difference < 0:
                reasons.append(f"Lower price (${abs(price_difference):.2f} less)")
            else:
                reasons.append(f"Premium option (${price_difference:.2f} more)")

            substitutes.append({
                'sku': cand_sku,
                'name': candidate.get('name', ''),
                'category': candidate.get('category', ''),
                'color': candidate.get('color', ''),
                'price': cand_price,
                'stock_quantity': cand_stock,
                'match_score': round(overall_match, 1),
                'price_difference': round(price_difference, 2),
                'reason': ' • '.join(reasons) if reasons else 'Similar product',
            })

        substitutes.sort(key=lambda x: x['match_score'], reverse=True)
        return substitutes[:max_substitutes]

    except Exception as e:
        print(f"Error finding substitutes for {sku}: {e}")
        return []


@tool
def get_product_stockout_details(sku: str) -> Dict:
    """
    Get detailed stockout analysis and substitutes for a specific product.

    Args:
        sku: Product SKU to analyze

    Returns:
        Dict with product details, stockout prediction, risk level, and substitute recommendations.
    """
    try:
        product = get_product_by_sku(sku)
        if not product:
            return {'status': 'error', 'error': f'Product {sku} not found'}

        current_stock = int(product.get('stock_quantity', product.get('inventory', 0)))

        if current_stock > 10:
            return {
                'status': 'in_stock',
                'message': 'Product is currently well-stocked',
                'stock_quantity': current_stock,
            }

        velocity = float(product.get('sales_velocity', 0.5))
        prediction = predict_stockout_date(current_stock, velocity)
        substitutes = find_product_substitutes(sku)

        return {
            'status': 'success',
            'product': {
                'sku': sku,
                'name': product.get('name', ''),
                'category': product.get('category', ''),
                'current_stock': current_stock,
                'stockout_prediction': prediction,
            },
            'substitutes': substitutes,
        }

    except Exception as e:
        print(f"Error getting stockout details for {sku}: {e}")
        return {'status': 'error', 'error': str(e)}


# ============================================================================
# STRANDS AGENT
# ============================================================================

bedrock_model = BedrockModel(
    model_id=os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
    temperature=float(os.getenv("MODEL_TEMPERATURE", "0.4")),
)

agent = Agent(
    model=bedrock_model,
    tools=[get_at_risk_inventory, find_product_substitutes, get_product_stockout_details],
    system_prompt=(
        "You are the HeartKart Stockout Sentinel Agent. Your mission is to predict stockouts "
        "before they happen and recommend substitute products for Valentine's Day inventory.\n\n"
        "Use your tools to:\n"
        "1. Identify at-risk products using get_at_risk_inventory\n"
        "2. Find substitute products using find_product_substitutes\n"
        "3. Analyze specific products using get_product_stockout_details\n\n"
        "Provide:\n"
        "- Critical insights on stockout patterns\n"
        "- Customer impact assessment\n"
        "- Substitute strategy recommendations\n"
        "- Preventive action items\n\n"
        "Be concise and actionable. Focus on Valentine's Day business impact."
    ),
)


# ============================================================================
# CORE REPORT BUILDER (structured output)
# ============================================================================

def generate_stockout_report() -> Dict:
    """Generate comprehensive stockout report with substitutes using Strands agent."""
    print("🔍 Analyzing stockout risks...")

    at_risk_products = get_at_risk_inventory(30)

    if not at_risk_products:
        return {
            'status': 'success',
            'message': 'No stockout risks detected!',
            'at_risk_products': [],
        }

    print(f"📊 Found {len(at_risk_products)} products at risk, fetching substitutes...")

    enriched = []
    category_stats = defaultdict(int)

    for product in at_risk_products:
        substitutes = find_product_substitutes(product['sku'])
        category_stats[product.get('category', 'unknown')] += 1

        enriched.append({
            **product,
            'substitutes': substitutes,
            'substitute_count': len(substitutes),
        })

    # Use Strands agent for AI insights
    print("🤖 Getting AI insights from Strands agent...")
    try:
        agent_response = agent(
            f"Analyze these {len(enriched)} at-risk Valentine's Day products and provide "
            f"critical insights, customer impact, substitute strategy, and preventive actions:\n"
            f"{json.dumps([{k: v for k, v in p.items() if k != 'substitutes'} for p in enriched[:10]], default=str)}"
        )
        ai_analysis = str(agent_response)
    except Exception as e:
        print(f"Error calling Strands agent: {e}")
        ai_analysis = (
            f"Stockout report generated for {len(enriched)} at-risk products. "
            f"Immediate action required to prevent Valentine's Day shortages."
        )

    critical_count = sum(1 for p in enriched if p['risk_level'] == 'CRITICAL')
    high_count = sum(1 for p in enriched if p['risk_level'] == 'HIGH')
    products_with_substitutes = sum(1 for p in enriched if p['substitute_count'] > 0)

    return {
        'status': 'success',
        'generated_at': datetime.now().isoformat(),
        'summary': {
            'total_at_risk': len(enriched),
            'critical_risk': critical_count,
            'high_risk': high_count,
            'products_with_substitutes': products_with_substitutes,
            'substitute_coverage': round(
                (products_with_substitutes / len(enriched) * 100), 1
            ) if enriched else 0,
            'categories_affected': dict(category_stats),
        },
        'ai_analysis': ai_analysis,
        'at_risk_products': enriched,
    }


# ============================================================================
# AGENTCORE RUNTIME ENTRY POINT
# ============================================================================

@app.entrypoint
def stockout_sentinel_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    AgentCore Runtime entry point for the Stockout Sentinel Agent.

    Args:
        payload: Input with optional action ('generate_report' or 'get_substitute') and sku

    Returns:
        Dictionary with stockout analysis and substitute recommendations
    """
    print(f"Received request: {json.dumps(payload, default=str)}")

    try:
        action = payload.get('action', 'generate_report')

        if action == 'get_substitute':
            sku = payload.get('sku')
            if not sku:
                return {'status': 'error', 'error': 'SKU required for get_substitute action'}
            result = get_product_stockout_details(sku)
        else:
            result = generate_stockout_report()

        print(f"Generated result with status: {result.get('status')}")
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
