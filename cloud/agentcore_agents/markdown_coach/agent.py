"""
Markdown & Clearance Coach Agent for AWS Bedrock AgentCore Runtime (Strands Framework)

Analyzes aged inventory and recommends optimal markdown pricing strategies
to maximize revenue recovery and minimize holding costs.
Uses the Strands framework with @tool decorators for all data access operations.
"""

import json
import os
import re
import sys
from datetime import datetime
from typing import Dict, List, Any
from collections import defaultdict

import boto3
from strands import tool, Agent
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# Initialize AgentCore App
app = BedrockAgentCoreApp()

# Import product data access layer (DynamoDB-based)
from product_data_access import get_all_products, get_products_by_category


# ============================================================================
# HELPER FUNCTIONS (pure calculations, not tools)
# ============================================================================

def categorize_age(days_remaining: float, velocity: float) -> str:
    """Categorize inventory age urgency."""
    if velocity == 0:
        return "DEAD_STOCK"
    elif days_remaining > 180:
        return "CRITICAL"
    elif days_remaining > 120:
        return "HIGH"
    elif days_remaining > 60:
        return "MEDIUM"
    else:
        return "NORMAL"


def calculate_markdown(days_remaining: float, velocity: float, quantity: int, current_price: float) -> Dict:
    """Calculate optimal markdown percentage for aged inventory."""
    if velocity == 0:
        markdown_pct = 50
        reason = "No sales activity — aggressive clearance needed"
    elif days_remaining > 180:
        markdown_pct = 35
        reason = "Critical aging — deep discount to move quickly"
    elif days_remaining > 120:
        markdown_pct = 25
        reason = "High aging — significant discount needed"
    elif days_remaining > 60:
        markdown_pct = 15
        reason = "Moderate aging — gentle markdown to accelerate sales"
    else:
        markdown_pct = 0
        reason = "Normal inventory turnover"

    new_price = current_price * (1 - markdown_pct / 100)
    potential_revenue = new_price * quantity

    return {
        'markdown_percentage': markdown_pct,
        'new_price': round(new_price, 2),
        'potential_revenue': round(potential_revenue, 2),
        'reason': reason,
        'urgency': 'HIGH' if markdown_pct >= 30 else 'MEDIUM' if markdown_pct >= 15 else 'LOW',
    }


# ============================================================================
# STRANDS TOOLS
# ============================================================================

@tool
def get_aged_inventory(age_threshold_days: int = 60) -> List[Dict]:
    """
    Identify products with aged inventory that need markdown pricing.

    Args:
        age_threshold_days: Minimum days of remaining supply to flag as aged (default: 60)

    Returns:
        List of aged products with sku, name, category, current_price, quantity,
        sales_velocity, days_remaining, age_category, and markdown_recommendation.
    """
    try:
        all_products = get_all_products(limit=1000)
        aged_products = []

        for product in all_products:
            velocity = float(product.get('sales_velocity', 0))
            quantity = int(product.get('stock_quantity', product.get('inventory', 0)))

            if quantity <= 0:
                continue

            days_remaining = quantity / velocity if velocity > 0 else 999

            if days_remaining > age_threshold_days or velocity == 0:
                age_category = categorize_age(days_remaining, velocity)
                current_price = float(product.get('price', 0))
                markdown_recommendation = calculate_markdown(
                    days_remaining, velocity, quantity, current_price
                )

                aged_products.append({
                    'sku': product.get('sku', ''),
                    'name': product.get('name', ''),
                    'category': product.get('category', ''),
                    'current_price': current_price,
                    'quantity': quantity,
                    'sales_velocity': velocity,
                    'days_remaining': round(days_remaining, 1),
                    'age_category': age_category,
                    'markdown_recommendation': markdown_recommendation,
                    'vendor': product.get('vendor_name', 'Unknown'),
                })

        aged_products.sort(key=lambda x: x['days_remaining'], reverse=True)
        return aged_products[:200]

    except Exception as e:
        print(f"Error analyzing aged inventory: {e}")
        return []


@tool
def get_bundle_suggestions(category: str = None) -> List[Dict]:
    """
    Suggest product bundles to help move aged inventory faster.

    Args:
        category: Category to build bundles from (None for all categories)

    Returns:
        List of bundle suggestions with bundle_name, items, regular_value,
        bundle_price, savings, and savings_percentage.
    """
    try:
        if category:
            products = get_products_by_category(category, limit=100)
        else:
            products = get_all_products(limit=1000)

        by_category: Dict[str, List] = defaultdict(list)
        for product in products:
            stock = int(product.get('stock_quantity', product.get('inventory', 0)))
            velocity = float(product.get('sales_velocity', 0))
            if stock > 10 and velocity < 0.5:
                cat = product.get('category', 'General')
                by_category[cat].append(product)

        bundles = []
        for cat, cat_products in by_category.items():
            if len(cat_products) >= 3:
                bundle_items = cat_products[:5]
                bundle_value = sum(float(p.get('price', 0)) for p in bundle_items)
                bundle_price = bundle_value * 0.7

                bundles.append({
                    'bundle_name': f"{cat} Clearance Bundle",
                    'items': [{'sku': p.get('sku', ''), 'name': p.get('name', '')} for p in bundle_items],
                    'regular_value': round(bundle_value, 2),
                    'bundle_price': round(bundle_price, 2),
                    'savings': round(bundle_value - bundle_price, 2),
                    'savings_percentage': 30,
                })

        return bundles[:20]

    except Exception as e:
        print(f"Error generating bundle suggestions: {e}")
        return []


@tool
def get_clearance_timeline(age_threshold_days: int = 60) -> Dict:
    """
    Create a phased clearance timeline for aged inventory.

    Args:
        age_threshold_days: Minimum days of supply to flag (default: 60)

    Returns:
        Dict with immediate, week_2, week_4, liquidation buckets.
    """
    try:
        aged_products = get_aged_inventory(age_threshold_days)

        timeline: Dict[str, List] = {
            'immediate': [],
            'week_2': [],
            'week_4': [],
            'liquidation': [],
        }

        for product in aged_products:
            age_cat = product['age_category']
            if age_cat in ['DEAD_STOCK', 'CRITICAL']:
                timeline['immediate'].append(product)
            elif age_cat == 'HIGH':
                timeline['week_2'].append(product)
            else:
                timeline['week_4'].append(product)

        return {
            'immediate': len(timeline['immediate']),
            'week_2': len(timeline['week_2']),
            'week_4': len(timeline['week_4']),
            'liquidation': len(timeline['liquidation']),
            'total': len(aged_products),
            'immediate_skus': [p['sku'] for p in timeline['immediate'][:10]],
        }

    except Exception as e:
        print(f"Error creating clearance timeline: {e}")
        return {'immediate': 0, 'week_2': 0, 'week_4': 0, 'liquidation': 0, 'total': 0}


# ============================================================================
# STRANDS AGENT
# ============================================================================

bedrock_model = BedrockModel(
    model_id=os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
    temperature=float(os.getenv("MODEL_TEMPERATURE", "0.7")),
)

agent = Agent(
    model=bedrock_model,
    tools=[get_aged_inventory, get_bundle_suggestions, get_clearance_timeline],
    system_prompt=(
        "You are the HeartKart Markdown & Clearance Coach Agent for a Valentine's Day "
        "gift retail platform based in India.\n\n"
        "IMPORTANT: All prices are in Indian Rupees (₹). ALWAYS use ₹ symbol, NEVER use $.\n"
        "Do NOT wrap your response in any XML tags.\n\n"
        "Use your tools to:\n"
        "1. Identify aged products using get_aged_inventory\n"
        "2. Suggest bundles using get_bundle_suggestions\n"
        "3. Create a phased timeline using get_clearance_timeline\n\n"
        "Provide:\n"
        "1. Overall clearance strategy (timing, channels, bundling opportunities)\n"
        "2. Category-specific recommendations\n"
        "3. Risk assessment (what if items don't sell at markdown)\n"
        "4. Alternative strategies (bundles, promotions, liquidation)\n\n"
        "Be concise and actionable. Focus on maximizing revenue recovery."
    ),
)


# ============================================================================
# CORE REPORT BUILDER (structured output)
# ============================================================================

def generate_markdown_report(age_threshold_days: int = 60) -> Dict:
    """Generate complete markdown and clearance report using Strands agent."""
    print("🏷️  Analyzing aged inventory...")
    aged_products = get_aged_inventory(age_threshold_days)
    print(f"📊 Found {len(aged_products)} aged items")

    if not aged_products:
        return {
            'status': 'success',
            'message': 'No aged inventory found',
            'aged_products': [],
            'summary': {
                'total_aged_items': 0,
                'total_aged_value': 0,
                'potential_revenue': 0,
                'recovery_rate': 0,
            },
        }

    total_aged_value = sum(p['current_price'] * p['quantity'] for p in aged_products)
    total_potential_revenue = sum(p['markdown_recommendation']['potential_revenue'] for p in aged_products)

    by_category: Dict[str, int] = defaultdict(int)
    for product in aged_products:
        by_category[product['category']] += 1

    print("🎯 Generating clearance plan with Strands agent...")
    try:
        agent_response = agent(
            f"I have {len(aged_products)} aged inventory items worth ₹{total_aged_value:,.2f}. "
            f"Please analyze the top aged items and provide a comprehensive clearance strategy:\n"
            f"Top items: {json.dumps(aged_products[:10], default=str)}\n"
            f"Categories affected: {json.dumps(dict(by_category), default=str)}"
        )
        ai_recommendations = re.sub(r'<thinking>.*?</thinking>', '', str(agent_response), flags=re.DOTALL).strip()
        ai_recommendations = re.sub(r'</?(?:response|answer|result|output|reply)>', '', ai_recommendations, flags=re.IGNORECASE).strip()
    except Exception as e:
        print(f"Error calling Strands agent: {e}")
        ai_recommendations = (
            f"Clearance strategy: Apply markdown pricing to {len(aged_products)} aged items. "
            f"Potential revenue recovery: ₹{total_potential_revenue:,.2f} "
            f"({(total_potential_revenue / total_aged_value * 100):.1f}% of current value)."
        )

    print("📅 Creating clearance timeline...")
    timeline = get_clearance_timeline(age_threshold_days)

    print("🎁 Generating bundle suggestions from aged products...")
    by_cat: Dict[str, List] = defaultdict(list)
    for product in aged_products:
        by_cat[product['category']].append(product)

    bundles = []
    for cat, cat_products in by_cat.items():
        if len(cat_products) >= 2:
            bundle_items = cat_products[:5]
            bundle_value = sum(float(p.get('current_price', 0)) for p in bundle_items)
            bundle_price = bundle_value * 0.7
            bundles.append({
                'bundle_name': f"{cat} Clearance Bundle",
                'items': [{'sku': p.get('sku', ''), 'name': p.get('name', '')} for p in bundle_items],
                'regular_value': round(bundle_value, 2),
                'bundle_price': round(bundle_price, 2),
                'savings': round(bundle_value - bundle_price, 2),
                'savings_percentage': 30,
            })

    return {
        'status': 'success',
        'generated_at': datetime.now().isoformat(),
        'summary': {
            'total_aged_items': len(aged_products),
            'total_aged_value': round(total_aged_value, 2),
            'potential_revenue': round(total_potential_revenue, 2),
            'recovery_rate': round(
                total_potential_revenue / total_aged_value * 100, 1
            ) if total_aged_value > 0 else 0,
        },
        'by_category': dict(by_category),
        'ai_recommendations': ai_recommendations,
        'aged_products': aged_products,
        'timeline': timeline,
        'suggested_bundles': bundles,
    }


# ============================================================================
# AGENTCORE RUNTIME ENTRY POINT
# ============================================================================

@app.entrypoint
def markdown_coach_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    AgentCore Runtime entry point for the Markdown Coach Agent.

    Args:
        payload: Input with optional 'age_threshold_days' (int) parameter

    Returns:
        Dictionary with markdown recommendations and clearance plan
    """
    print(f"Received request: {json.dumps(payload, default=str)}")

    try:
        age_threshold_days = payload.get('age_threshold_days', 60)
        result = generate_markdown_report(age_threshold_days)
        print(f"Generated report with {result['summary']['total_aged_items']} aged items")
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
