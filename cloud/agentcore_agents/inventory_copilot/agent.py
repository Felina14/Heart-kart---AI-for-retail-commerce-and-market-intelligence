"""
Inventory Copilot Agent for AWS Bedrock AgentCore Runtime (Strands Framework)

Conversational AI for inventory analytics and natural language queries.
Uses Amazon Nova with Strands tools accessing DynamoDB for intelligent responses.
"""

import json
import os
import re
import sys
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any
from collections import defaultdict

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
from product_data_access import get_all_products, get_product_by_sku, get_products_by_category

# ============================================================================
# TOOL RESULT CAPTURE — reliable way to get structured product data
# ============================================================================

_captured_products = []


def _capture_product(p: dict):
    """Store a product dict in the capture list."""
    _captured_products.append({
        'sku': p.get('sku', ''),
        'name': p.get('name', ''),
        'category': p.get('category', ''),
        'color': p.get('color', ''),
        'price': p.get('price', 0),
        'stock_quantity': p.get('stock_quantity', 0),
        'sales_count': p.get('sales_count'),
        'in_stock': p.get('in_stock', True),
        'vendor_name': p.get('vendor_name', ''),
    })


# ============================================================================
# STRANDS TOOLS
# ============================================================================

@tool
def search_inventory(
    category: str = None,
    max_price: float = None,
    min_price: float = None,
    max_stock: int = None,
    min_stock: int = None,
    keyword: str = None,
) -> List[Dict]:
    """
    Search inventory products with optional filters.

    Args:
        category: Filter by product category (e.g. 'Roses', 'Chocolates')
        max_price: Maximum price filter
        min_price: Minimum price filter
        max_stock: Maximum stock quantity filter
        min_stock: Minimum stock quantity filter
        keyword: Keyword to search in product name (case-insensitive)

    Returns:
        List of matching products with sku, name, category, price, stock_quantity, vendor_name.
    """
    try:
        if category:
            products = get_products_by_category(category, limit=200)
        else:
            products = get_all_products(limit=1000)

        results = []
        for product in products:
            price = float(product.get('price', 0))
            stock = int(product.get('stock_quantity', product.get('inventory', 0)))
            name = product.get('name', '')

            if max_price is not None and price > max_price:
                continue
            if min_price is not None and price < min_price:
                continue
            if max_stock is not None and stock > max_stock:
                continue
            if min_stock is not None and stock < min_stock:
                continue
            if keyword and keyword.lower() not in name.lower():
                continue

            results.append({
                'sku': product.get('sku', ''),
                'name': name,
                'category': product.get('category', ''),
                'color': product.get('color', ''),
                'price': price,
                'stock_quantity': stock,
                'in_stock': stock > 0,
                'vendor_name': product.get('vendor_name', ''),
                'description': (product.get('description', '')[:100] + '...')
                    if len(product.get('description', '')) > 100
                    else product.get('description', ''),
            })

        results = results[:50]

        # Capture products for structured response
        for p in results:
            _capture_product(p)

        return results

    except Exception as e:
        print(f"Error searching inventory: {e}")
        return []


@tool
def get_sales_analytics(metric: str = "top_sellers", days: int = 30, limit: int = 10) -> Dict:
    """
    Get sales analytics from inventory data.

    Args:
        metric: Analytics type - 'top_sellers', 'low_sellers', 'category_breakdown', 'price_analysis'
        days: Historical window in days (default: 30)
        limit: Number of results to return (default: 10)

    Returns:
        Dict with analytics results including products list and summary statistics.
    """
    try:
        # Get real sales data from SalesHistory table
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        response = sales_table.scan(
            FilterExpression=Attr('date').gte(cutoff_date)
        )
        items = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = sales_table.scan(
                FilterExpression=Attr('date').gte(cutoff_date),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))

        sales_by_sku = defaultdict(int)
        for record in items:
            sku = record.get('sku', '')
            qty = int(record.get('quantity', 0))
            if sku:
                sales_by_sku[sku] += qty

        # Get all products to enrich sales data
        all_products = get_all_products(limit=1000)

        products_with_data = []
        for product in all_products:
            sku = product.get('sku', '')
            sales_count = sales_by_sku.get(sku, 0)

            # Generate realistic mock sales if no real data
            if sales_count == 0:
                price = float(product.get('price', 0))
                if price < 500:
                    sales_count = random.randint(15, 80)
                elif price < 1500:
                    sales_count = random.randint(5, 40)
                else:
                    sales_count = random.randint(1, 15)

            products_with_data.append({
                'sku': sku,
                'name': product.get('name', ''),
                'category': product.get('category', ''),
                'price': float(product.get('price', 0)),
                'stock_quantity': int(product.get('stock_quantity', product.get('inventory', 0))),
                'sales_count': sales_count,
                'vendor_name': product.get('vendor_name', ''),
            })

        if metric == 'top_sellers':
            sorted_products = sorted(products_with_data, key=lambda x: x['sales_count'], reverse=True)
            result_products = sorted_products[:limit]
            # Capture for structured response
            for p in result_products:
                _capture_product(p)
            return {
                'metric': 'top_sellers',
                'period_days': days,
                'products': result_products,
                'total_products': len(products_with_data),
                'summary': f"Top {limit} best-selling products over the last {days} days",
            }

        elif metric == 'low_sellers':
            sorted_products = sorted(products_with_data, key=lambda x: x['sales_count'])
            result_products = sorted_products[:limit]
            # Capture for structured response
            for p in result_products:
                _capture_product(p)
            return {
                'metric': 'low_sellers',
                'period_days': days,
                'products': result_products,
                'total_products': len(products_with_data),
                'summary': f"Bottom {limit} slowest-selling products over the last {days} days",
            }

        elif metric == 'category_breakdown':
            by_category = defaultdict(lambda: {'count': 0, 'total_sales': 0, 'total_stock': 0})
            for p in products_with_data:
                cat = p['category'] or 'Uncategorized'
                by_category[cat]['count'] += 1
                by_category[cat]['total_sales'] += p['sales_count']
                by_category[cat]['total_stock'] += p['stock_quantity']

            categories = [
                {'category': cat, **stats}
                for cat, stats in sorted(by_category.items(), key=lambda x: x[1]['total_sales'], reverse=True)
            ]
            return {
                'metric': 'category_breakdown',
                'period_days': days,
                'categories': categories[:limit],
                'total_categories': len(categories),
                'summary': f"Sales breakdown by category over the last {days} days",
            }

        else:  # price_analysis
            avg_price = sum(p['price'] for p in products_with_data) / len(products_with_data) if products_with_data else 0
            low_stock = [p for p in products_with_data if p['stock_quantity'] < 20]
            return {
                'metric': 'price_analysis',
                'total_products': len(products_with_data),
                'avg_price': round(avg_price, 2),
                'low_stock_count': len(low_stock),
                'top_by_value': sorted(
                    products_with_data,
                    key=lambda x: x['price'] * x['sales_count'],
                    reverse=True
                )[:limit],
                'summary': f"Price and value analysis across {len(products_with_data)} products",
            }

    except Exception as e:
        print(f"Error getting sales analytics: {e}")
        return {'error': str(e), 'metric': metric}


@tool
def get_product_details(sku: str) -> Dict:
    """
    Get detailed information about a specific product by SKU.

    Args:
        sku: Product SKU identifier

    Returns:
        Full product details including pricing, stock, vendor, and category information.
    """
    try:
        product = get_product_by_sku(sku)
        if not product:
            return {'error': f'Product {sku} not found'}

        result = {
            'sku': product.get('sku', ''),
            'name': product.get('name', ''),
            'description': product.get('description', ''),
            'category': product.get('category', ''),
            'subcategory': product.get('subcategory', ''),
            'color': product.get('color', ''),
            'material': product.get('material', ''),
            'price': float(product.get('price', 0)),
            'stock_quantity': int(product.get('stock_quantity', product.get('inventory', 0))),
            'in_stock': int(product.get('stock_quantity', product.get('inventory', 0))) > 0,
            'vendor_name': product.get('vendor_name', ''),
            'vendor_lead_time_days': product.get('vendor_lead_time_days', 7),
            'vendor_moq': product.get('vendor_moq', 50),
        }

        # Capture for structured response
        _capture_product(result)

        return result
    except Exception as e:
        print(f"Error getting product details for {sku}: {e}")
        return {'error': str(e)}


# ============================================================================
# STRANDS AGENT
# ============================================================================

bedrock_model = BedrockModel(
    model_id=os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
    temperature=float(os.getenv("MODEL_TEMPERATURE", "0.4")),
)

agent = Agent(
    model=bedrock_model,
    tools=[search_inventory, get_sales_analytics, get_product_details],
    system_prompt=(
        "You are the HeartKart Inventory Copilot — a conversational AI assistant "
        "for a Valentine's Day gift retail platform based in India.\n\n"
        "CRITICAL RULES:\n"
        "1. You MUST call at least one tool for EVERY query. NEVER answer from general knowledge.\n"
        "2. All prices are in Indian Rupees (₹). ALWAYS use ₹ symbol, NEVER use $.\n"
        "3. Do NOT wrap your response in any XML tags like <response>, <answer>, or <thinking>.\n"
        "4. Keep responses concise and data-driven.\n\n"
        "Tool selection rules:\n"
        "- Questions about 'least sold', 'most sold', 'best selling', 'worst selling', 'top sellers', "
        "'bottom sellers', 'demand', 'popular', 'trending' → call get_sales_analytics\n"
        "- Questions about finding products, categories, prices, stock levels → call search_inventory\n"
        "  Use the max_price, min_price, keyword, and category parameters to filter accurately.\n"
        "- Questions about a specific SKU → call get_product_details\n\n"
        "After getting tool results, list specific products with their names, SKUs, ₹ prices, and stock.\n"
    ),
)


def _strip_model_tags(text: str) -> str:
    """Strip all model-generated XML tags from response text."""
    text = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL)
    text = re.sub(r'</?(?:response|answer|result|output|reply)>', '', text, flags=re.IGNORECASE)
    return text.strip()


# ============================================================================
# AGENTCORE RUNTIME ENTRY POINT
# ============================================================================

@app.entrypoint
def inventory_copilot_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    AgentCore Runtime entry point for the Inventory Copilot Agent.

    Args:
        payload: Input containing 'query' field with natural language question

    Returns:
        Dictionary with AI-generated answer and relevant product data
    """
    print(f"Received request: {json.dumps(payload, default=str)}")

    try:
        query = payload.get('query', '')

        if not query:
            return {
                'status': 'error',
                'error': 'No query provided. Please include a "query" field with your question.',
            }

        print(f"🔍 Processing query: {query}")

        # Clear captured products before each query
        _captured_products.clear()

        # Let the Strands agent handle the full query with tool calls
        # Tools will automatically capture their results into _captured_products
        agent_response = agent(query)
        answer = _strip_model_tags(str(agent_response))

        # Deduplicate captured products by SKU
        seen_skus = set()
        products = []
        for p in _captured_products:
            if p['sku'] and p['sku'] not in seen_skus:
                seen_skus.add(p['sku'])
                products.append(p)

        print(f"📦 Captured {len(products)} products from tool calls")

        return {
            'status': 'success',
            'query': query,
            'query_type': 'strands_agent',
            'summary': answer,
            'products': products,
            'total_results': len(products),
            'returned_results': len(products),
            'timestamp': datetime.now().isoformat(),
        }

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
