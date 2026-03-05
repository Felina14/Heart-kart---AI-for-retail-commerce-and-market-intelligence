#!/usr/bin/env python3
"""
Inventory Copilot Agent
Conversational AI for inventory analytics and queries
Uses Amazon Nova with access to DynamoDB
"""

import boto3
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any
from collections import defaultdict
from decimal import Decimal
from boto3.dynamodb.conditions import Attr

# Import product data access layer (project root is two levels up)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from product_data_access import get_all_products, get_product_by_sku, get_products_by_category

# Initialize AWS clients
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
sales_table = dynamodb.Table('SalesHistory')


def _scan_all(table, **kwargs):
    items = []
    response = table.scan(**kwargs)
    items.extend(response.get('Items', []))
    while 'LastEvaluatedKey' in response:
        kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
        response = table.scan(**kwargs)
        items.extend(response.get('Items', []))
    return items


def _to_num(v):
    if isinstance(v, Decimal):
        return int(v) if v % 1 == 0 else float(v)
    return v


def _normalize(p):
    return {k: _to_num(v) if isinstance(v, Decimal) else v for k, v in p.items()}


def get_sales_analytics() -> Dict:
    """Aggregate 30-day total sales per SKU from DynamoDB SalesHistory table."""
    try:
        cutoff = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        records = _scan_all(sales_table, FilterExpression=Attr('date').gte(cutoff))
        sales_by_sku = defaultdict(int)
        for r in records:
            sales_by_sku[r['sku']] += _to_num(r.get('quantity', 0))
        return dict(sales_by_sku)
    except Exception as e:
        print(f"Error fetching sales data: {e}")
        return {}


def determine_query_type(natural_query: str) -> str:
    """Determine if query needs analytics or simple search"""
    query_lower = natural_query.lower()
    
    # Analytics keywords
    analytics_keywords = [
        'least sold', 'most sold', 'best selling', 'worst selling',
        'top selling', 'bottom', 'slowest', 'fastest',
        'total sales', 'revenue', 'performance',
        'how many sold', 'sales velocity', 'trending'
    ]
    for keyword in analytics_keywords:
        if keyword in query_lower:
            return 'analytics'
    
    return 'search'


def handle_analytics_query(natural_query: str) -> Dict:
    """Handle analytical queries that need sales data."""
    print("📊 Detected analytics query - fetching sales data...")
    
    sales_by_sku = get_sales_analytics()
    
    try:
        raw = get_all_products(limit=1000)
        products = {}
        for p in raw:
            sku = p.get('sku', '')
            products[sku] = {
                'sku': sku,
                'name': p.get('name', ''),
                'category': p.get('category', ''),
                'price': float(p.get('price', 0)),
                'stock_quantity': int(p.get('stock_quantity', p.get('inventory', 0))),
                'sales_count': sales_by_sku.get(sku, 0),
                'vendor_name': p.get('vendor_name', '')
            }
    except Exception as e:
        return {'status': 'error', 'error': f'Failed to fetch products: {e}'}
    
    # Analyze with Nova
    context = {
        'query': natural_query,
        'total_products': len(products),
        'products_with_sales': len([p for p in products.values() if p['sales_count'] > 0]),
        'top_sellers': sorted(products.values(), key=lambda x: x['sales_count'], reverse=True)[:10],
        'least_sellers': sorted(products.values(), key=lambda x: x['sales_count'])[:10]
    }
    
    prompt = f"""You are an inventory analyst. Answer this question concisely using the data provided:

Question: "{natural_query}"

Data Available:
{json.dumps(context, indent=2)}

Provide a brief, conversational answer that includes:
- The specific answer to their question
- Key statistics (total products, products with sales, etc.)
- List the top 5-10 relevant products with their details
- Brief insights or recommendations if relevant

Keep it concise and natural. Don't use headers like "Direct Answer" or numbered sections."""

    try:
        response = bedrock.invoke_model(
            modelId='us.amazon.nova-lite-v1:0',
            body=json.dumps({
                'messages': [{'role': 'user', 'content': [{'text': prompt}]}],
                'inferenceConfig': {'temperature': 0.4, 'maxTokens': 2000}
            })
        )
        
        result = json.loads(response['body'].read())
        answer = result['output']['message']['content'][0]['text']
        
        # Extract relevant products for display
        if 'least' in natural_query.lower() or 'worst' in natural_query.lower() or 'slowest' in natural_query.lower():
            relevant_products = sorted(products.values(), key=lambda x: x['sales_count'])[:10]
        else:
            relevant_products = sorted(products.values(), key=lambda x: x['sales_count'], reverse=True)[:10]
        
        return {
            'status': 'success',
            'query': natural_query,
            'query_type': 'analytics',
            'summary': answer,
            'products': relevant_products,
            'total_results': len(relevant_products),
            'returned_results': len(relevant_products),
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        return {'status': 'error', 'error': f'Analytics failed: {e}'}


def execute_inventory_query(natural_query: str) -> Dict:
    """
    Execute a natural language query against inventory.
    Routes to analytics or search based on query type.
    For search queries: scans all products and uses Nova to filter/rank results.
    """
    print(f"🔍 Processing query: {natural_query}")

    query_type = determine_query_type(natural_query)
    if query_type == 'analytics':
        return handle_analytics_query(natural_query)

    # Fetch all products then let Nova pick the best matches
    try:
        all_products = get_all_products(limit=1000)
    except Exception as e:
        return {'status': 'error', 'error': f'Failed to fetch products: {e}', 'query': natural_query}

    schema_info = """
    DynamoDB Table: Products
    Fields: sku, name, category (Electronics, Apparel, Home & Kitchen, Toys, Sports,
            Beauty, Books, Garden, Automotive, Health), price (float),
            stock_quantity (int), sales_velocity (float), reorder_point (int),
            vendor_name, vendor_lead_time (int), vendor_moq (int),
            vendor_on_time_rate (float), stock_scenario
    """
    
    prompt = f"""{schema_info}

Natural Language Query: "{natural_query}"

Here is the full product catalog ({len(all_products)} items):
{json.dumps(all_products[:200], indent=2)}

Return ONLY a JSON array of the top matching SKUs (max 50) in this format:
["SKU-0001", "SKU-0042", ...]

Select SKUs that best match the query. Consider category, price, stock level, and name."""

    try:
        response = bedrock.invoke_model(
            modelId='us.amazon.nova-lite-v1:0',
            body=json.dumps({
                'messages': [{'role': 'user', 'content': [{'text': prompt}]}],
                'inferenceConfig': {'temperature': 0.1, 'maxTokens': 500}
            })
        )
        result = json.loads(response['body'].read())
        text = result['output']['message']['content'][0]['text'].strip()
        
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0].strip()
        elif '```' in text:
            text = text.split('```')[1].split('```')[0].strip()
        
        matched_skus = set(json.loads(text))
    except Exception as e:
        print(f"Error getting Nova filter: {e}")
        # Fallback: simple name/category keyword match
        kw = natural_query.lower()
        matched_skus = {p['sku'] for p in all_products
                        if kw in p.get('name', '').lower() or kw in p.get('category', '').lower()}

    products = [
        {
            'sku': p['sku'],
            'name': p['name'],
            'category': p.get('category', ''),
            'price': float(p.get('price', 0)),
            'stock_quantity': p.get('stock_quantity', 0),
            'in_stock': p.get('stock_quantity', 0) > 0,
            'vendor_name': p.get('vendor_name', ''),
            'sales_velocity': p.get('sales_velocity', 0)
        }
        for p in all_products if p['sku'] in matched_skus
    ]

    summary = generate_query_summary(natural_query, products, len(products))

    return {
        'status': 'success',
        'query': natural_query,
        'total_results': len(products),
        'returned_results': len(products),
        'summary': summary,
        'products': products,
        'timestamp': datetime.now().isoformat()
    }


def generate_query_summary(query: str, products: List[Dict], total: int) -> str:
    """Generate a natural language summary of query results"""
    
    if not products:
        return f"No products found matching '{query}'."
    
    # Calculate statistics
    avg_price = sum(p['price'] for p in products) / len(products) if products else 0
    low_stock_count = sum(1 for p in products if p['stock_quantity'] < 10)
    categories = list(set(p['category'] for p in products))
    
    context = {
        'query': query,
        'total_found': total,
        'showing': len(products),
        'avg_price': round(avg_price, 2),
        'low_stock_count': low_stock_count,
        'categories': categories[:5],
        'sample_products': [p['name'] for p in products[:3]]
    }
    
    prompt = f"""Summarize these inventory query results in 2-3 sentences:

Query: "{query}"
Results: {json.dumps(context, indent=2)}

Provide a helpful, conversational summary that highlights:
- How many products were found
- Key characteristics (price range, categories, stock levels)
- Any notable insights

Be concise and friendly."""

    try:
        response = bedrock.invoke_model(
            modelId='us.amazon.nova-lite-v1:0',
            body=json.dumps({
                'messages': [
                    {
                        'role': 'user',
                        'content': [{'text': prompt}]
                    }
                ],
                'inferenceConfig': {
                    'temperature': 0.5,
                    'maxTokens': 200
                }
            })
        )
        
        result = json.loads(response['body'].read())
        return result['output']['message']['content'][0]['text'].strip()
        
    except Exception as e:
        # Fallback summary
        return f"Found {total} products matching '{query}'. Showing {len(products)} results with an average price of ${avg_price:.2f}."


def get_query_suggestions() -> List[str]:
    """Get example queries users can try."""
    return [
        # Analytics queries
        "What is the least sold item?",
        "Show me the top 10 best selling products",
        # Search queries
        "Show me all Electronics under $50 with less than 10 in stock",
        "Find Apparel products that are low on stock",
        "What Home & Kitchen items do we have over $100?",
        "Show me Sports products from ActiveGear Supply",
        "Find Beauty products under $20",
        "What Health items are in stock?"
    ]


if __name__ == '__main__':
    print("=" * 70)
    print("💬 INVENTORY COPILOT - Natural Language Queries")
    print("=" * 70)
    
    # Example queries
    test_queries = [
        "Show me all wreaths under $50 with less than 10 in stock",
        "Find red ornaments",
        "What Valentine gift items do we have?"
    ]
    
    for query in test_queries:
        print(f"\n{'='*70}")
        result = execute_inventory_query(query)
        
        if result['status'] == 'success':
            print(f"\n✅ Query: {result['query']}")
            print(f"📊 Found: {result['total_results']} products")
            print(f"\n💡 Summary: {result['summary']}")
            print(f"\n📦 Top Results:")
            for i, product in enumerate(result['products'][:5], 1):
                print(f"  {i}. {product['name']} - ${product['price']:.2f} ({product['stock_quantity']} in stock)")
        else:
            print(f"\n❌ Error: {result['error']}")
    
    print(f"\n{'='*70}")
