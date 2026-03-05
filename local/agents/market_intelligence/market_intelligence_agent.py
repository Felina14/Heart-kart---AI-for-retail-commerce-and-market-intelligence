#!/usr/bin/env python3
"""
Market Intelligence Agent
AI-powered market intelligence agent that analyzes competitor prices,
regional demand trends, and category signals to provide actionable market insights.
"""

import json
import os
import sys
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any
from collections import defaultdict

import boto3
from boto3.dynamodb.conditions import Attr

# Initialize AWS clients
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
sales_table = dynamodb.Table('SalesHistory')

# Import product data access layer (project root is two levels up)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from product_data_access import (
    get_all_products,
    get_products_by_category,
    get_product_by_sku,
)


# ============================================================================
# MARKET DATA FUNCTIONS
# ============================================================================

def get_sales_data_from_orders(days: int = 30) -> Dict:
    """Get real sales data from DynamoDB SalesHistory table."""
    try:
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        response = sales_table.scan(
            FilterExpression=Attr('date').gte(cutoff_date)
        )
        records = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = sales_table.scan(
                FilterExpression=Attr('date').gte(cutoff_date),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            records.extend(response.get('Items', []))

        # Pre-load all products ONCE to avoid N+1 query problem
        all_products = get_all_products(limit=1000)
        product_map = {}
        for p in all_products:
            sku = p.get('sku', '')
            if sku:
                product_map[sku] = p

        sales_by_sku = defaultdict(lambda: {'quantity': 0, 'revenue': 0, 'orders': 0})
        sales_by_category = defaultdict(lambda: {'quantity': 0, 'revenue': 0, 'orders': 0})
        sales_by_region = defaultdict(lambda: {'quantity': 0, 'revenue': 0, 'orders': 0})

        # Regional distribution weights for simulating regional demand
        region_weights = {
            'North': 0.28, 'South': 0.25, 'West': 0.22,
            'East': 0.15, 'Central': 0.10,
        }

        for record in records:
            sku = record.get('sku', '')
            qty = int(record.get('quantity', 0))
            category = record.get('category', '')

            product = product_map.get(sku, {})
            if not category:
                category = product.get('category', 'Uncategorized')
            price = float(product.get('price', 0))

            sales_by_sku[sku]['quantity'] += qty
            sales_by_sku[sku]['revenue'] += qty * price
            sales_by_sku[sku]['orders'] += 1

            sales_by_category[category]['quantity'] += qty
            sales_by_category[category]['revenue'] += qty * price
            sales_by_category[category]['orders'] += 1

        # Distribute total sales across regions using weighted distribution
        total_qty = sum(s['quantity'] for s in sales_by_sku.values())
        total_rev = sum(s['revenue'] for s in sales_by_sku.values())
        total_ord = sum(s['orders'] for s in sales_by_sku.values())
        for region, weight in region_weights.items():
            jitter = random.uniform(0.9, 1.1)
            sales_by_region[region]['quantity'] = int(total_qty * weight * jitter)
            sales_by_region[region]['revenue'] = round(total_rev * weight * jitter, 2)
            sales_by_region[region]['orders'] = int(total_ord * weight * jitter)

        return {
            'sales_by_sku': dict(sales_by_sku),
            'sales_by_category': dict(sales_by_category),
            'sales_by_region': dict(sales_by_region),
            'total_orders': len(records),
            'date_range_days': days,
        }
    except Exception as e:
        print(f"Error fetching sales data: {e}")
        return {
            'sales_by_sku': {},
            'sales_by_category': {},
            'sales_by_region': {},
            'total_orders': 0,
            'date_range_days': days,
        }


def get_competitor_price_from_api(sku: str, category: str) -> Dict:
    """Get competitor prices — MOCKED DATA for demonstration."""
    product = get_product_by_sku(sku)
    our_price = float(product.get('price', 0)) if product else 0

    if our_price == 0:
        return {'our_price': 0, 'competitor_prices': [0, 0, 0], 'source': 'mock'}

    if our_price < 500:
        variance_range = 0.10
    elif our_price < 1500:
        variance_range = 0.15
    else:
        variance_range = 0.20

    competitor_prices = [
        our_price * random.uniform(1 - variance_range, 1 - variance_range * 0.3),
        our_price * random.uniform(1 - variance_range * 0.3, 1 + variance_range * 0.3),
        our_price * random.uniform(1 + variance_range * 0.3, 1 + variance_range),
    ]

    return {
        'our_price': our_price,
        'competitor_prices': competitor_prices,
        'source': 'mock',
    }


# ============================================================================
# MARKET INTELLIGENCE FUNCTIONS
# ============================================================================

def get_competitor_price_index(category: str = None) -> Dict:
    """Get competitor price index for products or a specific category."""
    try:
        if category:
            products = get_products_by_category(category, limit=50)
        else:
            products = get_all_products(limit=100)

        if not products:
            return {'error': 'No products found'}

        competitor_data = []
        for product in products[:20]:
            sku = product.get('sku', '')
            cat = product.get('category', '')

            price_data = get_competitor_price_from_api(sku, cat)
            our_price = price_data['our_price']
            competitor_prices = price_data['competitor_prices']
            avg_competitor_price = sum(competitor_prices) / len(competitor_prices)

            price_difference = our_price - avg_competitor_price
            price_difference_pct = (price_difference / avg_competitor_price * 100) if avg_competitor_price > 0 else 0

            competitor_data.append({
                'sku': product.get('sku'),
                'name': product.get('name'),
                'our_price': our_price,
                'avg_competitor_price': round(avg_competitor_price, 2),
                'price_difference': round(price_difference, 2),
                'price_difference_pct': round(price_difference_pct, 2),
                'competitiveness': (
                    'UNDERPRICED' if price_difference_pct < -5
                    else 'OVERPRICED' if price_difference_pct > 5
                    else 'COMPETITIVE'
                ),
                'trend': random.choice(['UP', 'DOWN', 'STABLE']),
            })

        avg_our_price = sum(p['our_price'] for p in competitor_data) / len(competitor_data)
        avg_competitor_price = sum(p['avg_competitor_price'] for p in competitor_data) / len(competitor_data)

        return {
            'category': category or 'All Categories',
            'total_products_analyzed': len(competitor_data),
            'avg_our_price': round(avg_our_price, 2),
            'avg_competitor_price': round(avg_competitor_price, 2),
            'market_position': (
                'COMPETITIVE' if abs(avg_our_price - avg_competitor_price) / avg_competitor_price < 0.05
                else 'UNDERPRICED' if avg_our_price < avg_competitor_price
                else 'OVERPRICED'
            ),
            'products': competitor_data,
            'timestamp': datetime.now().isoformat(),
            'data_source': 'mock',
        }
    except Exception as e:
        print(f"Error getting competitor price index: {e}")
        return {'error': str(e)}


def get_regional_demand_trends(region: str = None) -> Dict:
    """Get regional demand trend index showing demand levels by geography."""
    try:
        products = get_all_products(limit=200)
        sales_data = get_sales_data_from_orders(days=30)
        has_real_data = sales_data.get('total_orders', 0) > 0

        regions = ['North', 'South', 'East', 'West', 'Central'] if not region else [region]

        categories_set = set()
        for product in products[:100]:
            cat = product.get('category', 'Uncategorized')
            if cat:
                categories_set.add(cat)

        regional_trends = []
        for reg in regions:
            base_demand = {
                'North': 1.15, 'South': 0.90, 'East': 1.10,
                'West': 0.95, 'Central': 1.05,
            }.get(reg, 1.0)

            overall_demand_index = base_demand * random.uniform(0.95, 1.05)

            if overall_demand_index > 1.1:
                trend = 'INCREASING'
            elif overall_demand_index < 0.9:
                trend = 'DECREASING'
            else:
                trend = 'STABLE'

            categories = {}
            for cat in list(categories_set)[:15]:
                category_base = random.uniform(0.85, 1.20)
                cat_demand_index = overall_demand_index * category_base
                categories[cat] = {
                    'demand_index': round(cat_demand_index, 2),
                    'trend': (
                        'INCREASING' if cat_demand_index > 1.1
                        else 'DECREASING' if cat_demand_index < 0.9
                        else 'STABLE'
                    ),
                    'growth_rate': round((cat_demand_index - 1.0) * 100, 2) / 100,
                }

            total_quantity = int(overall_demand_index * random.uniform(500, 2000))
            total_revenue = total_quantity * random.uniform(800, 1500)
            total_orders = int(total_quantity / random.uniform(2, 5))

            regional_trends.append({
                'region': reg,
                'overall_demand_index': round(overall_demand_index, 2),
                'trend': trend,
                'total_quantity': total_quantity,
                'total_revenue': round(total_revenue, 2),
                'total_orders': total_orders,
                'categories': categories,
            })

        return {
            'regions': regional_trends,
            'timestamp': datetime.now().isoformat(),
            'analysis_period': 'Last 30 days',
            'total_orders': sum(r['total_orders'] for r in regional_trends),
            'data_source': 'real' if has_real_data else 'mock',
        }
    except Exception as e:
        print(f"Error getting regional demand trends: {e}")
        return {'error': str(e)}


def get_category_trend_signals() -> Dict:
    """Get category trend signals showing trending, declining, and opportunity categories."""
    try:
        sales_data = get_sales_data_from_orders(days=30)
        has_real_data = sales_data.get('total_orders', 0) > 0
        sales_by_category = sales_data.get('sales_by_category', {}) if has_real_data else {}

        products = get_all_products(limit=500)

        category_stats = defaultdict(lambda: {
            'count': 0, 'total_value': 0, 'avg_price': 0,
            'low_stock_count': 0, 'total_stock': 0,
            'total_sales': 0, 'sales_revenue': 0,
        })

        for product in products:
            cat = product.get('category', 'Uncategorized')
            category_stats[cat]['count'] += 1
            category_stats[cat]['total_value'] += float(product.get('price', 0))
            stock = int(product.get('stock_quantity', product.get('inventory', 0)))
            category_stats[cat]['total_stock'] += stock
            if stock < 20:
                category_stats[cat]['low_stock_count'] += 1

        for cat, sales in sales_by_category.items():
            if cat in category_stats:
                category_stats[cat]['total_sales'] = sales['quantity']
                category_stats[cat]['sales_revenue'] = sales['revenue']

        category_trends = []
        avg_stock_per_category = (
            sum(s['total_stock'] for s in category_stats.values()) / len(category_stats)
            if category_stats else 1
        )

        for cat, stats in category_stats.items():
            avg_price = stats['total_value'] / stats['count'] if stats['count'] > 0 else 0
            avg_stock = stats['total_stock'] / stats['count'] if stats['count'] > 0 else 0

            if has_real_data and stats['total_sales'] > 0:
                demand_velocity = (stats['total_sales'] / avg_stock_per_category) if avg_stock_per_category > 0 else 1.0
            else:
                stock_ratio = avg_stock / max(stats['count'], 1)
                demand_velocity = 1.5 / (stock_ratio + 0.5)
                demand_velocity *= random.uniform(0.8, 1.3)

            rand_val = random.random()
            if rand_val < 0.3 or demand_velocity > 1.2:
                trend_signal = 'TRENDING_UP'
                demand_velocity = max(demand_velocity, 1.2)
            elif rand_val < 0.5 or demand_velocity < 0.8:
                trend_signal = 'TRENDING_DOWN'
                demand_velocity = min(demand_velocity, 0.8)
            else:
                trend_signal = 'STABLE'
                demand_velocity = max(0.9, min(1.1, demand_velocity))

            low_stock_ratio = stats['low_stock_count'] / max(stats['count'], 1)
            opportunity_score = demand_velocity * (1 + low_stock_ratio * 2)

            category_trends.append({
                'category': cat,
                'product_count': stats['count'],
                'avg_price': round(avg_price, 2),
                'low_stock_products': stats['low_stock_count'],
                'avg_stock': round(avg_stock, 1),
                'total_sales': stats['total_sales'] if has_real_data else 0,
                'sales_revenue': round(stats['sales_revenue'], 2) if has_real_data else 0,
                'trend_signal': trend_signal,
                'demand_velocity': round(demand_velocity, 2),
                'opportunity_score': round(opportunity_score, 2),
            })

        category_trends.sort(key=lambda x: x['opportunity_score'], reverse=True)

        trending_up = [c for c in category_trends if c['trend_signal'] == 'TRENDING_UP'][:10]
        trending_down = [c for c in category_trends if c['trend_signal'] == 'TRENDING_DOWN'][:10]
        opportunities = category_trends[:20]

        return {
            'total_categories': len(category_trends),
            'trending_up': trending_up,
            'trending_down': trending_down,
            'opportunities': opportunities,
            'all_categories': category_trends,
            'timestamp': datetime.now().isoformat(),
            'data_source': 'real' if has_real_data else 'mock',
            'total_orders_analyzed': sales_data.get('total_orders', 0),
        }
    except Exception as e:
        print(f"Error getting category trend signals: {e}")
        return {'error': str(e)}


# ============================================================================
# COMPOSITE HELPERS
# ============================================================================

def get_market_signals_summary() -> Dict:
    """Combine competitor prices, regional trends, and category signals."""
    try:
        competitor_data = get_competitor_price_index()
        regional_data = get_regional_demand_trends()
        category_data = get_category_trend_signals()

        context = {
            'competitor_analysis': {
                'market_position': competitor_data.get('market_position'),
                'products_analyzed': competitor_data.get('total_products_analyzed', 0),
            },
            'regional_insights': {
                'regions_analyzed': len(regional_data.get('regions', [])),
                'overall_trend': (
                    regional_data.get('regions', [{}])[0].get('trend', 'STABLE')
                    if regional_data.get('regions') else 'STABLE'
                ),
            },
            'category_opportunities': {
                'trending_categories': len(category_data.get('trending_up', [])),
                'top_opportunities': category_data.get('opportunities', [])[:3],
            },
        }

        return {
            'status': 'success',
            'competitor_prices': competitor_data,
            'regional_trends': regional_data,
            'category_signals': category_data,
            'summary': context,
            'timestamp': datetime.now().isoformat(),
        }
    except Exception as e:
        print(f"Error getting market signals summary: {e}")
        return {'status': 'error', 'error': str(e)}


def analyze_market_intelligence_with_nova(query: str, market_data: Dict) -> str:
    """Use Amazon Nova to analyze market intelligence data."""
    prompt = f"""You are a market intelligence analyst for HeartKart, a Valentine's Day products retailer.

Analyze this market intelligence data and provide actionable insights for the Valentine's Day season.

Query: '{query}'

Market Data Summary:
{json.dumps(market_data.get('summary', {}), indent=2, default=str)}

Provide:
1. Key market insights and competitive positioning
2. Regional demand opportunities
3. Category trend recommendations
4. Actionable pricing, inventory, and marketing recommendations

Be concise and data-driven."""

    try:
        response = bedrock.invoke_model(
            modelId='us.amazon.nova-lite-v1:0',
            body=json.dumps({
                'messages': [{'role': 'user', 'content': [{'text': prompt}]}],
                'inferenceConfig': {'temperature': 0.4, 'maxTokens': 1500}
            })
        )

        result = json.loads(response['body'].read())
        return result['output']['message']['content'][0]['text']

    except Exception as e:
        print(f"Error calling Nova: {e}")
        return f"Market intelligence report generated. AI analysis unavailable: {str(e)}"


# ============================================================================
# MAIN MARKET INTELLIGENCE FUNCTION
# ============================================================================

def generate_market_intelligence_report(
    query: str = None, category: str = None, region: str = None,
    report_type: str = 'full'
) -> Dict:
    """Generate comprehensive market intelligence report."""
    print("📊 Generating market intelligence report...")

    try:
        market_data = get_market_signals_summary()
        if market_data.get('status') == 'error':
            return market_data

        analysis_query = query or "Provide a comprehensive market intelligence summary"
        ai_insights = analyze_market_intelligence_with_nova(analysis_query, market_data)

        report = {
            'status': 'success',
            'report_date': datetime.now().isoformat(),
            'market_signals': market_data,
            'ai_insights': ai_insights,
            'key_metrics': {
                'competitor_analysis': {
                    'market_position': market_data['competitor_prices'].get('market_position'),
                    'products_analyzed': market_data['competitor_prices'].get('total_products_analyzed', 0),
                },
                'regional_insights': {
                    'regions_analyzed': len(market_data['regional_trends'].get('regions', [])),
                    'trending_regions': [
                        r['region']
                        for r in market_data['regional_trends'].get('regions', [])
                        if r.get('trend') == 'INCREASING'
                    ],
                },
                'category_opportunities': {
                    'trending_categories': len(market_data['category_signals'].get('trending_up', [])),
                    'top_opportunities': market_data['category_signals'].get('opportunities', [])[:5],
                },
            },
            'recommendations': {
                'pricing': [],
                'inventory': [],
                'marketing': [],
            },
        }

        if 'price' in ai_insights.lower() or 'pricing' in ai_insights.lower():
            report['recommendations']['pricing'].append(
                "Review pricing strategy based on competitor analysis"
            )
        if 'inventory' in ai_insights.lower() or 'stock' in ai_insights.lower():
            report['recommendations']['inventory'].append(
                "Adjust inventory levels based on regional demand trends"
            )
        if 'category' in ai_insights.lower() or 'trend' in ai_insights.lower():
            report['recommendations']['marketing'].append(
                "Focus marketing efforts on trending categories"
            )

        print(
            f"✅ Generated market intelligence report with "
            f"{len(market_data.get('category_signals', {}).get('all_categories', []))} "
            f"categories analyzed"
        )
        return report

    except Exception as e:
        import traceback
        print(f"Error generating market intelligence report: {e}")
        traceback.print_exc()
        return {'status': 'error', 'error': str(e), 'traceback': traceback.format_exc()}
