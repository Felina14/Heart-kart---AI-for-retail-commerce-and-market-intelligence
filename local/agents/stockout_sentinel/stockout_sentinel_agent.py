#!/usr/bin/env python3
"""
Stockout Sentinel Agent
Predicts stockouts and suggests intelligent product substitutes
Uses Amazon Nova for smart recommendations
"""

import boto3
import json
import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import defaultdict
from decimal import Decimal

# Initialize AWS clients
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# Import product data access layer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from product_data_access import (
    get_all_products,
    get_product_by_sku,
    get_products_by_category,
    search_products,
    get_low_stock_products as get_low_stock_from_db,
)


def calculate_sales_velocity(sku: str, days: int = 30) -> float:
    """Return sales_velocity stored on the product record."""
    try:
        product = get_product_by_sku(sku)
        if product:
            v = product.get('sales_velocity')
            if v is not None:
                try:
                    return float(v)
                except Exception:
                    pass
        return 0.5
    except Exception:
        return 0.5


def predict_stockout_date(sku: str, current_stock: int, velocity: float) -> Dict:
    """Predict when a product will stock out"""
    if velocity <= 0:
        return {
            'days_until_stockout': 999,
            'stockout_date': None,
            'risk_level': 'LOW'
        }
    
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
        'risk_level': risk_level
    }


def find_substitute_products(product: Dict, max_substitutes: int = 5) -> List[Dict]:
    """
    Find substitute products — same category, similar price (±30%), in stock.
    """
    try:
        category = product.get('category', '')
        price = float(product.get('price', 0))
        sku = product.get('sku', '')
        min_price = price * 0.7
        max_price = price * 1.3
        
        all_products = get_products_by_category(category, limit=500)
        if not all_products:
            all_products = get_all_products(limit=1000)
        
        substitutes = []
        for sub_product in all_products:
            if sub_product.get('sku') == sku:
                continue
            
            sub_stock = int(sub_product.get('stock_quantity', sub_product.get('inventory', 0)) or 0)
            sub_price = float(sub_product.get('price', 0))
            
            if sub_stock <= 5 or sub_price < min_price or sub_price > max_price:
                continue
            
            category_match = 1.0 if sub_product.get('category') == category else 0.5
            color_match = 1.0 if sub_product.get('color') == product.get('color') else 0.3
            price_diff = abs(sub_price - price) / price if price > 0 else 1.0
            price_match = max(0, 1.0 - price_diff)
            
            overall_match = (category_match * 0.4 + color_match * 0.3 + price_match * 0.3) * 100
            
            substitutes.append({
                'sku': sub_product.get('sku', ''),
                'name': sub_product.get('name', ''),
                'category': sub_product.get('category', ''),
                'color': sub_product.get('color', ''),
                'price': sub_price,
                'stock_quantity': sub_stock,
                'match_score': round(overall_match, 1),
                'price_difference': round(sub_price - price, 2),
                'reason': generate_substitute_reason(product, sub_product, category_match, color_match)
            })
        
        substitutes.sort(key=lambda x: x['match_score'], reverse=True)
        return substitutes[:max_substitutes]
        
    except Exception as e:
        print(f"Error finding substitutes: {e}")
        return []


def generate_substitute_reason(original: Dict, substitute: Dict, category_match: float, color_match: float) -> str:
    """Generate human-readable reason for substitute recommendation"""
    reasons = []
    
    if category_match == 1.0:
        reasons.append(f"Same category ({substitute.get('category')})")
    
    if color_match == 1.0:
        reasons.append(f"Same color ({substitute.get('color')})")
    elif substitute.get('color'):
        reasons.append(f"Alternative color ({substitute.get('color')})")
    
    price_diff = float(substitute.get('price', 0)) - float(original.get('price', 0))
    if abs(price_diff) < 5:
        reasons.append("Similar price")
    elif price_diff < 0:
        reasons.append(f"Lower price (${abs(price_diff):.2f} less)")
    else:
        reasons.append(f"Premium option (${price_diff:.2f} more)")
    
    return " • ".join(reasons) if reasons else "Similar product"


def analyze_stockout_with_nova(stockout_data: List[Dict]) -> str:
    """Use Amazon Nova to analyze stockout patterns and provide insights"""
    
    context = {
        'total_at_risk': len(stockout_data),
        'critical_items': [item for item in stockout_data if item['risk_level'] == 'CRITICAL'],
        'categories_affected': list(set(item['category'] for item in stockout_data)),
        'analysis_date': datetime.now().isoformat()
    }
    
    prompt = f"""You are a retail inventory analyst for HeartKart, a Valentine's Day products retailer.

Stockout Risk Analysis:
{json.dumps(context, indent=2)}

Analyze the stockout situation and provide:

1. **Critical Insights**: What patterns do you see? (categories, price ranges)
2. **Customer Impact**: How will these stockouts affect the shopping experience?
3. **Substitute Strategy**: How should we guide customers to alternatives?
4. **Preventive Actions**: What can we do to avoid similar situations?

Be concise and actionable. Focus on maintaining customer satisfaction during the Valentine's Day season."""

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
                    'temperature': 0.4,
                    'maxTokens': 1500
                }
            })
        )
        
        result = json.loads(response['body'].read())
        return result['output']['message']['content'][0]['text']
        
    except Exception as e:
        print(f"Error calling Nova: {e}")
        return "AI analysis unavailable"


def generate_stockout_report() -> Dict:
    """
    Main function: Generate comprehensive stockout report with substitutes
    """
    print("🔍 Analyzing stockout risks...")
    
    try:
        low_stock = get_low_stock_from_db(threshold=30, limit=200)
        products = low_stock
    except Exception as e:
        print(f"Error fetching products: {e}")
        return {'status': 'error', 'error': str(e)}
    
    if not products:
        return {
            'status': 'success',
            'message': 'No stockout risks detected!',
            'at_risk_products': []
        }
    
    print(f"📊 Analyzing {len(products)} products at risk...")

    at_risk_products = []
    category_stats = defaultdict(int)
    color_stats = defaultdict(int)

    for product in products:
        sku = product.get('sku', '')
        current_stock = int(product.get('stock_quantity', product.get('inventory', 0)) or 0)

        velocity = calculate_sales_velocity(sku, days=30)
        stockout_prediction = predict_stockout_date(sku, current_stock, velocity)

        if stockout_prediction['days_until_stockout'] > 14:
            continue

        substitutes = find_substitute_products(product, max_substitutes=5)

        category_stats[product.get('category', 'unknown')] += 1
        color_stats[product.get('color', 'unknown')] += 1

        at_risk_products.append({
            'sku': sku,
            'name': product['name'],
            'category': product.get('category', ''),
            'color': product.get('color', ''),
            'price': float(product.get('price', 0)),
            'current_stock': current_stock,
            'sales_velocity': velocity,
            'days_until_stockout': stockout_prediction['days_until_stockout'],
            'stockout_date': stockout_prediction['stockout_date'],
            'risk_level': stockout_prediction['risk_level'],
            'substitutes': substitutes,
            'substitute_count': len(substitutes)
        })
    
    risk_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
    at_risk_products.sort(key=lambda x: (risk_order[x['risk_level']], x['days_until_stockout']))
    
    # Get AI analysis
    print("🤖 Getting AI insights from Amazon Nova...")
    ai_analysis = analyze_stockout_with_nova(at_risk_products)
    
    critical_count = sum(1 for p in at_risk_products if p['risk_level'] == 'CRITICAL')
    high_count = sum(1 for p in at_risk_products if p['risk_level'] == 'HIGH')
    products_with_substitutes = sum(1 for p in at_risk_products if p['substitute_count'] > 0)
    
    return {
        'status': 'success',
        'generated_at': datetime.now().isoformat(),
        'summary': {
            'total_at_risk': len(at_risk_products),
            'critical_risk': critical_count,
            'high_risk': high_count,
            'products_with_substitutes': products_with_substitutes,
            'substitute_coverage': round((products_with_substitutes / len(at_risk_products) * 100), 1) if at_risk_products else 0,
            'categories_affected': dict(category_stats),
            'colors_affected': dict(color_stats)
        },
        'ai_analysis': ai_analysis,
        'at_risk_products': at_risk_products
    }


def get_substitute_for_product(sku: str) -> Dict:
    """
    Get substitute recommendations for a specific product.
    """
    try:
        product = get_product_by_sku(sku)
        if not product:
            return {'status': 'error', 'error': 'Product not found'}
        
        current_stock = int(product.get('stock_quantity', product.get('inventory', 0)) or 0)
        
        if current_stock > 10:
            return {
                'status': 'in_stock',
                'message': 'Product is currently in stock',
                'stock_quantity': current_stock
            }
        
        velocity = calculate_sales_velocity(sku, days=30)
        stockout_prediction = predict_stockout_date(sku, current_stock, velocity)
        substitutes = find_substitute_products(product, max_substitutes=5)
        
        return {
            'status': 'success',
            'product': {
                'sku': sku,
                'name': product['name'],
                'current_stock': current_stock,
                'stockout_prediction': stockout_prediction
            },
            'substitutes': substitutes
        }
        
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


if __name__ == '__main__':
    print("=" * 70)
    print("🎯 STOCKOUT SENTINEL - Powered by Amazon Nova")
    print("=" * 70)
    
    report = generate_stockout_report()
    
    if report['status'] == 'success':
        summary = report.get('summary', {})
        
        print(f"\n📊 SUMMARY")
        print(f"  Products at risk: {summary.get('total_at_risk', 0)}")
        print(f"  Critical risk: {summary.get('critical_risk', 0)}")
        print(f"  High risk: {summary.get('high_risk', 0)}")
        print(f"  Products with substitutes: {summary.get('products_with_substitutes', 0)}")
        print(f"  Substitute coverage: {summary.get('substitute_coverage', 0)}%")
        
        print(f"\n🎨 Categories Affected:")
        for category, count in summary.get('categories_affected', {}).items():
            print(f"    {category}: {count} products")
        
        print(f"\n🤖 AI ANALYSIS:")
        print(report.get('ai_analysis', 'No analysis available'))
        
        print(f"\n🚨 TOP 10 CRITICAL STOCKOUTS:")
        print("-" * 70)
        
        for i, product in enumerate(report['at_risk_products'][:10], 1):
            print(f"\n{i}. {product['name']} ({product['sku']})")
            print(f"   Risk: {product['risk_level']} | Stock: {product['current_stock']} units")
            print(f"   Stockout in: {product['days_until_stockout']} days ({product['stockout_date']})")
            print(f"   Velocity: {product['sales_velocity']}/day")
            
            if product['substitutes']:
                print(f"   \n   💡 Substitutes ({len(product['substitutes'])}):")
                for sub in product['substitutes'][:3]:
                    print(f"      • {sub['name']} (${sub['price']:.2f}) - {sub['match_score']}% match")
                    print(f"        {sub['reason']}")
        
        with open('stockout_report.json', 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        print(f"\n✅ Full report saved to: stockout_report.json")
    
    print("\n" + "=" * 70)
