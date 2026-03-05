#!/usr/bin/env python3
"""
Markdown & Clearance Coach Agent
Analyzes aged inventory and recommends optimal markdown pricing strategies
"""

import boto3
import json
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from boto3.dynamodb.conditions import Attr

# Import product data access layer (project root is two levels up)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from product_data_access import get_all_products, get_products_by_category


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


class MarkdownCoachAgent:
    def __init__(self):
        self.region = 'us-east-1'
        self.bedrock = boto3.client('bedrock-runtime', region_name=self.region)
    
    def analyze_aged_inventory(self, age_threshold_days=60):
        """
        Identify aged inventory that needs markdown.
        
        Args:
            age_threshold_days: Products older than this need attention
        
        Returns:
            List of aged products with markdown recommendations
        """
        products = get_all_products(limit=1000)
        
        aged_products = []
        current_date = datetime.now()
        
        for product in products:
            velocity = product.get('sales_velocity', 0)
            quantity = product.get('stock_quantity', 0)
            
            if velocity > 0:
                days_remaining = quantity / velocity
            else:
                days_remaining = 999
            
            if days_remaining > age_threshold_days or velocity == 0:
                age_category = self._categorize_age(days_remaining, velocity)
                markdown_recommendation = self._calculate_markdown(
                    days_remaining, velocity, quantity, product.get('price', 0)
                )
                
                aged_products.append({
                    'sku': product.get('sku'),
                    'name': product.get('name'),
                    'category': product.get('category'),
                    'current_price': product.get('price', 0),
                    'quantity': quantity,
                    'sales_velocity': velocity,
                    'days_remaining': round(days_remaining, 1),
                    'age_category': age_category,
                    'markdown_recommendation': markdown_recommendation,
                    'vendor': product.get('vendor_name', 'Unknown')
                })
        
        aged_products.sort(key=lambda x: x['days_remaining'], reverse=True)
        
        return aged_products
    
    def _categorize_age(self, days_remaining, velocity):
        """Categorize inventory age"""
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
    
    def _calculate_markdown(self, days_remaining, velocity, quantity, current_price):
        """
        Calculate optimal markdown percentage
        
        Strategy:
        - Dead stock (no sales): 40-60% off
        - Critical (>180 days): 30-40% off
        - High (>120 days): 20-30% off
        - Medium (>60 days): 10-20% off
        """
        if velocity == 0:
            markdown_pct = 50
            reason = "No sales activity - aggressive clearance needed"
        elif days_remaining > 180:
            markdown_pct = 35
            reason = "Critical aging - deep discount to move quickly"
        elif days_remaining > 120:
            markdown_pct = 25
            reason = "High aging - significant discount needed"
        elif days_remaining > 60:
            markdown_pct = 15
            reason = "Moderate aging - gentle markdown to accelerate sales"
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
            'urgency': 'HIGH' if markdown_pct >= 30 else 'MEDIUM' if markdown_pct >= 15 else 'LOW'
        }
    
    def generate_clearance_plan(self, aged_products):
        """
        Generate a comprehensive clearance plan using AI
        """
        total_aged_value = sum(p['current_price'] * p['quantity'] for p in aged_products)
        total_potential_revenue = sum(p['markdown_recommendation']['potential_revenue'] for p in aged_products)
        
        by_category = {}
        for product in aged_products:
            cat = product['category']
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(product)
        
        prompt = f"""You are a retail pricing strategist. Analyze this aged inventory and provide a clearance plan.

AGED INVENTORY SUMMARY:
- Total aged items: {len(aged_products)}
- Current inventory value: ${total_aged_value:,.2f}
- Potential revenue after markdown: ${total_potential_revenue:,.2f}
- Revenue recovery rate: {(total_potential_revenue/total_aged_value*100):.1f}%

TOP 10 AGED ITEMS:
{json.dumps(aged_products[:10], indent=2)}

CATEGORIES AFFECTED:
{json.dumps({cat: len(items) for cat, items in by_category.items()}, indent=2)}

Provide:
1. Overall clearance strategy (timing, channels, bundling)
2. Category-specific recommendations
3. Risk assessment (what if items don't sell even at markdown)
4. Alternative strategies (donations, liquidation, bundles)

Keep response concise and actionable."""

        try:
            response = self.bedrock.invoke_model(
                modelId='amazon.nova-micro-v1:0',
                body=json.dumps({
                    "messages": [{"role": "user", "content": [{"text": prompt}]}],
                    "inferenceConfig": {"temperature": 0.7, "maxTokens": 1000}
                })
            )

            result = json.loads(response['body'].read())
            ai_recommendations = result['output']['message']['content'][0]['text']
        except Exception as e:
            print(f"Error calling Bedrock: {e}")
            ai_recommendations = (
                "Clearance plan: prioritize DEAD_STOCK and CRITICAL items first, "
                "bundle slow movers, and run a 2-4 week phased markdown campaign. "
                "Use deeper discounts for dead stock and moderate discounts for medium aging."
            )
        
        return {
            'summary': {
                'total_aged_items': len(aged_products),
                'total_aged_value': round(total_aged_value, 2),
                'potential_revenue': round(total_potential_revenue, 2),
                'recovery_rate': round(total_potential_revenue/total_aged_value*100, 1) if total_aged_value > 0 else 0
            },
            'by_category': {cat: len(items) for cat, items in by_category.items()},
            'ai_recommendations': ai_recommendations,
            'aged_products': aged_products
        }
    
    def get_clearance_timeline(self, aged_products):
        """
        Create a phased clearance timeline
        """
        buckets: dict = {
            'immediate': [],
            'week_2': [],
            'week_4': [],
            'liquidation': []
        }

        for product in aged_products:
            age_cat = product['age_category']

            if age_cat in ('DEAD_STOCK', 'CRITICAL'):
                buckets['immediate'].append(product)
            elif age_cat == 'HIGH':
                buckets['week_2'].append(product)
            else:
                buckets['week_4'].append(product)

        return {
            'immediate': len(buckets['immediate']),
            'week_2': len(buckets['week_2']),
            'week_4': len(buckets['week_4']),
            'liquidation': len(buckets['liquidation']),
            'total': len(aged_products),
        }
    
    def suggest_bundles(self, aged_products):
        """
        Suggest product bundles to move aged inventory
        """
        by_category = {}
        for product in aged_products:
            cat = product['category']
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(product)
        
        bundles = []
        
        for category, products in by_category.items():
            if len(products) >= 2:
                bundle_items = products[:5]
                bundle_value = sum(p['current_price'] for p in bundle_items)
                bundle_price = bundle_value * 0.7
                
                bundles.append({
                    'bundle_name': f"{category} Clearance Bundle",
                    'items': [{'sku': p['sku'], 'name': p['name']} for p in bundle_items],
                    'regular_value': round(bundle_value, 2),
                    'bundle_price': round(bundle_price, 2),
                    'savings': round(bundle_value - bundle_price, 2),
                    'savings_percentage': 30
                })
        
        return bundles


def generate_markdown_report():
    """Generate complete markdown and clearance report"""
    agent = MarkdownCoachAgent()
    
    print("🏷️  Analyzing aged inventory...")
    aged_products = agent.analyze_aged_inventory(age_threshold_days=60)
    
    print(f"\n📊 Found {len(aged_products)} aged items")
    
    if len(aged_products) == 0:
        return {
            'status': 'success',
            'message': 'No aged inventory found',
            'aged_products': []
        }
    
    print("\n🎯 Generating clearance plan...")
    clearance_plan = agent.generate_clearance_plan(aged_products)
    
    print("\n📅 Creating clearance timeline...")
    timeline = agent.get_clearance_timeline(aged_products)
    
    print("\n🎁 Suggesting product bundles...")
    bundles = agent.suggest_bundles(aged_products)
    
    return {
        'status': 'success',
        'generated_at': datetime.now().isoformat(),
        'summary': clearance_plan['summary'],
        'by_category': clearance_plan['by_category'],
        'ai_recommendations': clearance_plan['ai_recommendations'],
        'aged_products': aged_products,
        'timeline': timeline,
        'suggested_bundles': bundles
    }


if __name__ == '__main__':
    report = generate_markdown_report()
    print("\n" + "="*80)
    print("MARKDOWN & CLEARANCE REPORT")
    print("="*80)
    print(json.dumps(report, indent=2))
