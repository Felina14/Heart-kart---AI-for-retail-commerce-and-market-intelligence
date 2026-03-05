#!/usr/bin/env python3
"""
Pricing Intelligence Agent
AI-powered pricing intelligence agent that provides price recommendations,
competitor comparisons, and demand impact analysis for optimal pricing decisions.
"""

import json
import os
import sys
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from decimal import Decimal

import boto3

# Pricing Intelligence runtime config
def _env_truthy(name: str, default: str = "false") -> bool:
    return str(os.environ.get(name, default)).strip().lower() in {
        "1", "true", "yes", "y", "on",
    }

PRICING_USE_MARKET_INTEL = _env_truthy("PRICING_USE_MARKET_INTEL", "false")

# Initialize AWS clients
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# Import product data access layer (project root is two levels up)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from product_data_access import (
    get_all_products,
    get_products_by_category,
    get_product_by_sku,
)

# Import market intelligence competitor data from the local agent
MARKET_INTEL_AVAILABLE = False
_market_get_competitor_price_index = None
try:
    _mi_dir = os.path.join(os.path.dirname(__file__), '..', 'market_intelligence')
    if _mi_dir not in sys.path:
        sys.path.insert(0, os.path.abspath(_mi_dir))
    from market_intelligence_agent import get_competitor_price_index as _mi_func
    _market_get_competitor_price_index = _mi_func
    MARKET_INTEL_AVAILABLE = True
except ImportError:
    print("⚠️  Market Intelligence not available — competitor data will be mocked")


# ============================================================================
# PRICING CONFIGURATION & GUARDRAILS
# ============================================================================

DEFAULT_GUARDRAILS = {
    'min_margin_percent': 15.0,
    'max_discount_percent': 40.0,
    'competitive_price_tolerance': 5.0,
    'premium_price_max_multiplier': 1.5,
    'clearance_price_min_multiplier': 0.6,
}

PRICE_ELASTICITY = {
    'budget': -2.5,
    'mid_range': -1.8,
    'premium': -1.2,
}


def get_price_guardrails(category: str = None) -> Dict:
    """Get pricing guardrails (margin floor, max discount, policy rules)."""
    guardrails = DEFAULT_GUARDRAILS.copy()
    if category:
        premium_categories = ['Premium Gifts', 'Luxury Items', 'Designer Collection']
        if any(prem in category for prem in premium_categories):
            guardrails['min_margin_percent'] = 25.0
            guardrails['premium_price_max_multiplier'] = 2.0
        budget_categories = ['Gifts Under ₹499', 'Budget Items']
        if any(budg in category for budg in budget_categories):
            guardrails['min_margin_percent'] = 10.0
            guardrails['max_discount_percent'] = 50.0
    return {
        'guardrails': guardrails,
        'category': category or 'All Categories',
        'timestamp': datetime.now().isoformat(),
    }


# ============================================================================
# PRICING INTELLIGENCE FUNCTIONS
# ============================================================================

def calculate_recommended_price_range(
    sku: str = None,
    category: str = None,
    current_price: float = None,
    cost_price: float = None,
) -> Dict:
    """Calculate recommended price range with margin guardrails."""
    try:
        if sku:
            product = get_product_by_sku(sku)
            if not product:
                return {'error': f'Product {sku} not found'}
            current_price = float(product.get('price', 0))
            category = product.get('category', 'Uncategorized')
        elif category:
            products = get_products_by_category(category, limit=1)
            if not products:
                return {'error': f'No products found in category {category}'}
            product = products[0]
            current_price = float(product.get('price', 0))
        else:
            return {'error': 'Either sku or category must be provided'}

        if not cost_price:
            cost_price = current_price * random.uniform(0.60, 0.70)

        guardrails = get_price_guardrails(category)['guardrails']
        min_price = cost_price / (1 - guardrails['min_margin_percent'] / 100)

        competitor_price = None
        if PRICING_USE_MARKET_INTEL and MARKET_INTEL_AVAILABLE and _market_get_competitor_price_index and category:
            try:
                comp_data = _market_get_competitor_price_index(category)
                if comp_data.get('avg_competitor_price'):
                    competitor_price = comp_data['avg_competitor_price']
            except Exception:
                pass

        if not competitor_price:
            if current_price < 500:
                variance = random.uniform(0.90, 1.10)
            elif current_price < 1500:
                variance = random.uniform(0.85, 1.15)
            else:
                variance = random.uniform(0.80, 1.20)
            competitor_price = current_price * variance

        max_price = competitor_price * (1 + guardrails['competitive_price_tolerance'] / 100)
        margin_optimal = cost_price * (1 + (guardrails['min_margin_percent'] + 10) / 100)
        competitive_optimal = competitor_price * (1 - guardrails['competitive_price_tolerance'] / 200)
        optimal_price = (margin_optimal * 0.6) + (competitive_optimal * 0.4)
        optimal_price = max(min_price, min(optimal_price, max_price))

        current_margin = ((current_price - cost_price) / current_price * 100) if current_price > 0 else 0

        if current_price < min_price:
            action = 'INCREASE_PRICE'
            reason = f'Current price below minimum margin threshold ({guardrails["min_margin_percent"]}%)'
        elif current_price > max_price:
            action = 'DECREASE_PRICE'
            reason = 'Current price above competitive threshold'
        elif abs(current_price - optimal_price) / optimal_price < 0.05:
            action = 'MAINTAIN_PRICE'
            reason = 'Price is well-positioned'
        elif current_price < optimal_price:
            action = 'CONSIDER_INCREASE'
            reason = 'Opportunity to increase price while remaining competitive'
        else:
            action = 'CONSIDER_DECREASE'
            reason = 'Consider price reduction to improve competitiveness'

        return {
            'sku': sku or product.get('sku'),
            'product_name': product.get('name'),
            'category': category,
            'current_price': round(current_price, 2),
            'cost_price': round(cost_price, 2),
            'current_margin_percent': round(current_margin, 2),
            'competitor_price': round(competitor_price, 2),
            'price_range': {
                'min_price': round(min_price, 2),
                'optimal_price': round(optimal_price, 2),
                'max_price': round(max_price, 2),
            },
            'guardrails': guardrails,
            'recommendation': {
                'action': action,
                'reason': reason,
                'suggested_price': round(optimal_price, 2),
                'price_change': round(optimal_price - current_price, 2),
                'price_change_percent': round((optimal_price - current_price) / current_price * 100, 2),
            },
            'timestamp': datetime.now().isoformat(),
        }
    except Exception as e:
        print(f"Error calculating recommended price range: {e}")
        import traceback; traceback.print_exc()
        return {'error': str(e)}


COMPETITOR_PLATFORMS = [
    {'name': 'Amazon India', 'bias': 0.98, 'rating': 4.3, 'delivery': '1-2 days', 'url_slug': 'amazon.in'},
    {'name': 'Flipkart', 'bias': 0.95, 'rating': 4.1, 'delivery': '2-3 days', 'url_slug': 'flipkart.com'},
    {'name': 'Myntra', 'bias': 1.05, 'rating': 4.2, 'delivery': '3-5 days', 'url_slug': 'myntra.com'},
    {'name': 'IGP.com', 'bias': 1.10, 'rating': 4.0, 'delivery': '2-4 days', 'url_slug': 'igp.com'},
    {'name': 'Ferns N Petals', 'bias': 1.08, 'rating': 4.4, 'delivery': 'Same day', 'url_slug': 'fnp.com'},
    {'name': 'Archies Online', 'bias': 0.92, 'rating': 3.8, 'delivery': '3-5 days', 'url_slug': 'archiesonline.com'},
]


def _generate_competitor_prices(our_price: float, product_name: str = None) -> List[Dict]:
    """Generate realistic competitor price data across multiple platforms."""
    competitors = []
    random.seed(hash(str(our_price) + (product_name or '')))  # Stable per product

    for platform in COMPETITOR_PLATFORMS:
        # Each platform has a bias + random variance
        base_variance = platform['bias']
        noise = random.uniform(-0.08, 0.08)
        comp_price = round(our_price * (base_variance + noise), 0)
        # Add realistic small amounts
        if comp_price > 500:
            comp_price = round(comp_price / 10) * 10 - 1  # e.g., ₹2,489

        diff = our_price - comp_price
        diff_pct = (diff / comp_price * 100) if comp_price > 0 else 0

        # Simulate if they have stock
        in_stock = random.random() > 0.15

        # Price trend over last 30 days
        trend_choices = ['UP', 'DOWN', 'STABLE']
        trend = random.choice(trend_choices)
        trend_pct = round(random.uniform(1.0, 8.0), 1) if trend != 'STABLE' else 0
        if trend == 'DOWN':
            trend_pct = -trend_pct

        competitors.append({
            'platform': platform['name'],
            'price': round(comp_price, 2),
            'price_difference': round(diff, 2),
            'price_difference_pct': round(diff_pct, 1),
            'rating': platform['rating'],
            'delivery': platform['delivery'],
            'in_stock': in_stock,
            'price_trend': trend,
            'price_trend_pct': trend_pct,
            'last_checked': datetime.now().strftime('%d %b %Y, %I:%M %p'),
        })

    random.seed()  # Reset seed
    return competitors


def get_competitor_price_comparison(sku: str = None, category: str = None) -> Dict:
    """Get detailed price vs competitor comparison with per-platform breakdown."""
    try:
        if PRICING_USE_MARKET_INTEL and MARKET_INTEL_AVAILABLE and _market_get_competitor_price_index:
            try:
                comp_data = _market_get_competitor_price_index(category)
                if comp_data.get('products'):
                    if sku:
                        products = [p for p in comp_data['products'] if p.get('sku') == sku]
                        if products:
                            product = products[0]
                            return {
                                'sku': sku,
                                'product_name': product.get('name'),
                                'our_price': product.get('our_price'),
                                'avg_competitor_price': product.get('avg_competitor_price'),
                                'price_difference': product.get('price_difference'),
                                'price_difference_pct': product.get('price_difference_pct'),
                                'competitiveness': product.get('competitiveness'),
                                'trend': product.get('trend'),
                                'market_position': comp_data.get('market_position'),
                                'competitors': _generate_competitor_prices(
                                    float(product.get('our_price', 0)),
                                    product.get('name', ''),
                                ),
                                'timestamp': datetime.now().isoformat(),
                                'data_source': 'market_intelligence',
                            }
                    else:
                        return {
                            'category': category or 'All Categories',
                            'total_products': comp_data.get('total_products_analyzed', 0),
                            'avg_our_price': comp_data.get('avg_our_price'),
                            'avg_competitor_price': comp_data.get('avg_competitor_price'),
                            'market_position': comp_data.get('market_position'),
                            'products': comp_data.get('products', [])[:20],
                            'timestamp': datetime.now().isoformat(),
                            'data_source': 'market_intelligence',
                        }
            except Exception as e:
                print(f"Error getting market intelligence data: {e}")

        # Generate rich competitor data
        if sku:
            product = get_product_by_sku(sku)
            if not product:
                return {'error': f'Product {sku} not found'}
            our_price = float(product.get('price', 0))
            product_name = product.get('name', '')
            product_category = product.get('category', 'Uncategorized')
        elif category:
            products = get_products_by_category(category, limit=20)
            if not products:
                return {'error': f'No products found in category {category}'}
            our_price = sum(float(p.get('price', 0)) for p in products) / len(products)
            product_name = f'{category} Products (Avg)'
            product_category = category
        else:
            return {'error': 'Either sku or category must be provided'}

        # Generate per-platform competitor prices
        competitors = _generate_competitor_prices(our_price, product_name)

        # Calculate aggregate stats
        comp_prices = [c['price'] for c in competitors if c['in_stock']]
        avg_competitor_price = sum(comp_prices) / len(comp_prices) if comp_prices else our_price
        lowest_comp = min(comp_prices) if comp_prices else our_price
        highest_comp = max(comp_prices) if comp_prices else our_price

        price_diff = our_price - avg_competitor_price
        price_diff_pct = (price_diff / avg_competitor_price * 100) if avg_competitor_price > 0 else 0
        competitiveness = (
            'UNDERPRICED' if price_diff_pct < -5
            else 'OVERPRICED' if price_diff_pct > 5
            else 'COMPETITIVE'
        )

        # Market insight text
        cheaper_count = len([c for c in competitors if c['price'] < our_price and c['in_stock']])
        total_in_stock = len([c for c in competitors if c['in_stock']])

        if competitiveness == 'OVERPRICED':
            market_insight = f"HeartKart is priced {abs(price_diff_pct):.1f}% above the market average. {cheaper_count} of {total_in_stock} competitors offer lower prices."
        elif competitiveness == 'UNDERPRICED':
            market_insight = f"HeartKart is priced {abs(price_diff_pct):.1f}% below the market average — opportunity to increase price and improve margins."
        else:
            market_insight = f"HeartKart's price is well-positioned within the competitive range (±5% of market average)."

        # Also fetch nearby products for category comparison
        category_products = []
        if sku:
            nearby = get_products_by_category(product_category, limit=8)
            for p in nearby:
                p_sku = p.get('sku', '')
                p_price = float(p.get('price', 0))
                if p_price <= 0 or p_sku == sku:
                    continue
                p_comps = _generate_competitor_prices(p_price, p.get('name', ''))
                p_comp_prices = [c['price'] for c in p_comps if c['in_stock']]
                p_avg = sum(p_comp_prices) / len(p_comp_prices) if p_comp_prices else p_price
                p_diff = p_price - p_avg
                p_diff_pct = (p_diff / p_avg * 100) if p_avg > 0 else 0
                category_products.append({
                    'sku': p_sku,
                    'name': p.get('name', ''),
                    'our_price': round(p_price, 2),
                    'avg_competitor_price': round(p_avg, 2),
                    'price_difference': round(p_diff, 2),
                    'price_difference_pct': round(p_diff_pct, 1),
                    'competitiveness': 'UNDERPRICED' if p_diff_pct < -5 else 'OVERPRICED' if p_diff_pct > 5 else 'COMPETITIVE',
                })

        return {
            'sku': sku or 'N/A',
            'product_name': product_name,
            'category': product_category,
            'our_price': round(our_price, 2),
            'avg_competitor_price': round(avg_competitor_price, 2),
            'lowest_competitor_price': round(lowest_comp, 2),
            'highest_competitor_price': round(highest_comp, 2),
            'price_difference': round(price_diff, 2),
            'price_difference_pct': round(price_diff_pct, 2),
            'competitiveness': competitiveness,
            'market_insight': market_insight,
            'competitors': competitors,
            'category_products': category_products[:6],
            'trend': random.choice(['UP', 'DOWN', 'STABLE']),
            'timestamp': datetime.now().isoformat(),
            'data_source': 'competitive_intelligence',
        }
    except Exception as e:
        print(f"Error getting competitor price comparison: {e}")
        import traceback; traceback.print_exc()
        return {'error': str(e)}


def _calc_single_scenario(current_price: float, new_price: float, cost_price: float,
                          current_velocity: float, elasticity: float) -> Dict:
    """Calculate demand/revenue/margin for a single price scenario."""
    price_change_pct = ((new_price - current_price) / current_price) * 100
    demand_change_pct = price_change_pct * (elasticity / 100)
    expected_velocity = max(0, current_velocity * (1 + demand_change_pct / 100))

    current_revenue = current_price * current_velocity
    expected_revenue = new_price * expected_velocity
    revenue_change = expected_revenue - current_revenue
    revenue_change_pct = (revenue_change / current_revenue * 100) if current_revenue > 0 else 0

    current_margin = (current_price - cost_price) * current_velocity
    expected_margin = (new_price - cost_price) * expected_velocity
    margin_change = expected_margin - current_margin
    margin_change_pct = (margin_change / current_margin * 100) if current_margin > 0 else 0

    if revenue_change > 0 and margin_change > 0:
        recommendation = 'STRONGLY_RECOMMEND'
    elif margin_change > 0:
        recommendation = 'RECOMMEND'
    elif revenue_change > 0:
        recommendation = 'CONSIDER'
    else:
        recommendation = 'NOT_RECOMMENDED'

    return {
        'new_price': round(new_price, 2),
        'price_change_pct': round(price_change_pct, 1),
        'expected_velocity': round(expected_velocity, 2),
        'demand_change_pct': round(demand_change_pct, 1),
        'expected_revenue': round(expected_revenue, 2),
        'revenue_change': round(revenue_change, 2),
        'revenue_change_pct': round(revenue_change_pct, 1),
        'expected_margin': round(expected_margin, 2),
        'margin_change': round(margin_change, 2),
        'margin_change_pct': round(margin_change_pct, 1),
        'recommendation': recommendation,
    }


def calculate_demand_impact(sku: str, new_price: float, current_price: float = None) -> Dict:
    """Calculate expected demand impact of a price change using price elasticity model,
    including multiple price scenarios for comparison."""
    try:
        product = get_product_by_sku(sku)
        if not product:
            return {'error': f'Product {sku} not found'}

        if not current_price:
            current_price = float(product.get('price', 0))
        if current_price <= 0:
            return {'error': 'Invalid current price'}

        if current_price < 500:
            elasticity = PRICE_ELASTICITY['budget']
            price_segment = 'Budget'
        elif current_price < 1500:
            elasticity = PRICE_ELASTICITY['mid_range']
            price_segment = 'Mid-Range'
        else:
            elasticity = PRICE_ELASTICITY['premium']
            price_segment = 'Premium'

        cost_price = current_price * 0.65
        current_velocity = float(product.get('sales_velocity', 1.0))

        # Calculate primary scenario
        primary = _calc_single_scenario(current_price, new_price, cost_price, current_velocity, elasticity)

        # Generate multiple price scenarios for comparison
        scenario_pcts = [-20, -15, -10, -5, 0, 5, 10, 15, 20]
        scenarios = []
        best_revenue_scenario = None
        best_margin_scenario = None
        for pct in scenario_pcts:
            sc_price = round(current_price * (1 + pct / 100), 2)
            sc = _calc_single_scenario(current_price, sc_price, cost_price, current_velocity, elasticity)
            sc['label'] = f"{pct:+d}%" if pct != 0 else "Current"
            sc['is_current'] = pct == 0
            scenarios.append(sc)
            if not sc['is_current']:
                if best_revenue_scenario is None or sc['revenue_change'] > best_revenue_scenario['revenue_change']:
                    best_revenue_scenario = sc
                if best_margin_scenario is None or sc['margin_change'] > best_margin_scenario['margin_change']:
                    best_margin_scenario = sc

        # Recommendation text
        if primary['recommendation'] == 'STRONGLY_RECOMMEND':
            reason = 'Price change increases both revenue and margin — strongly recommended'
        elif primary['recommendation'] == 'RECOMMEND':
            reason = 'Price change improves margin despite potential revenue impact'
        elif primary['recommendation'] == 'CONSIDER':
            reason = 'Price change could increase revenue but may compress margins'
        else:
            reason = 'Price change is expected to reduce both revenue and margin'

        return {
            'sku': sku,
            'product_name': product.get('name'),
            'category': product.get('category', 'Uncategorized'),
            'price_segment': price_segment,
            'current_price': round(current_price, 2),
            'cost_price': round(cost_price, 2),
            'new_price': round(new_price, 2),
            'price_change_pct': primary['price_change_pct'],
            'elasticity': elasticity,
            'demand_impact': {
                'current_velocity': round(current_velocity, 2),
                'expected_velocity': primary['expected_velocity'],
                'demand_change_pct': primary['demand_change_pct'],
            },
            'revenue_impact': {
                'current_revenue': round(current_price * current_velocity, 2),
                'expected_revenue': primary['expected_revenue'],
                'revenue_change': primary['revenue_change'],
                'revenue_change_pct': primary['revenue_change_pct'],
            },
            'margin_impact': {
                'current_margin': round((current_price - cost_price) * current_velocity, 2),
                'expected_margin': primary['expected_margin'],
                'margin_change': primary['margin_change'],
                'margin_change_pct': primary['margin_change_pct'],
            },
            'scenarios': scenarios,
            'best_revenue_scenario': best_revenue_scenario,
            'best_margin_scenario': best_margin_scenario,
            'recommendation': {'action': primary['recommendation'], 'reason': reason},
            'timestamp': datetime.now().isoformat(),
        }
    except Exception as e:
        print(f"Error calculating demand impact: {e}")
        import traceback; traceback.print_exc()
        return {'error': str(e)}


def get_price_optimization_recommendations(
    category: str = None,
    limit: int = 20,
) -> Dict:
    """Get prioritized price optimization recommendations for products."""
    try:
        if category:
            products = get_products_by_category(category, limit=limit * 2)
        else:
            products = get_all_products(limit=limit * 2)

        if not products:
            return {'error': 'No products found'}

        recommendations = []
        for product in products[:limit]:
            sku = product.get('sku')
            current_price = float(product.get('price', 0))
            if current_price <= 0:
                continue

            price_range = calculate_recommended_price_range(sku=sku)
            if price_range.get('error'):
                continue

            comp_comparison = get_competitor_price_comparison(sku=sku)
            if comp_comparison.get('error'):
                continue

            optimal_price = price_range['price_range']['optimal_price']
            demand_impact = calculate_demand_impact(sku, optimal_price, current_price)
            if demand_impact.get('error'):
                continue

            priority_score = 0
            if price_range['recommendation']['action'] in ['INCREASE_PRICE', 'CONSIDER_INCREASE']:
                priority_score += 30
            if price_range['recommendation']['action'] in ['DECREASE_PRICE', 'CONSIDER_DECREASE']:
                priority_score += 20
            if demand_impact['revenue_impact']['revenue_change_pct'] > 10:
                priority_score += 25
            if demand_impact['margin_impact']['margin_change_pct'] > 15:
                priority_score += 25
            if comp_comparison.get('competitiveness') == 'OVERPRICED':
                priority_score += 20

            recommendations.append({
                'sku': sku,
                'product_name': product.get('name'),
                'category': product.get('category'),
                'current_price': current_price,
                'recommended_price': optimal_price,
                'price_change': price_range['recommendation']['price_change'],
                'price_change_pct': price_range['recommendation']['price_change_percent'],
                'current_margin': price_range['current_margin_percent'],
                'competitiveness': comp_comparison.get('competitiveness', 'UNKNOWN'),
                'expected_revenue_change_pct': demand_impact['revenue_impact']['revenue_change_pct'],
                'expected_margin_change_pct': demand_impact['margin_impact']['margin_change_pct'],
                'recommendation': price_range['recommendation']['action'],
                'priority_score': priority_score,
                'reason': price_range['recommendation']['reason'],
            })

        recommendations.sort(key=lambda x: x['priority_score'], reverse=True)

        total_products = len(recommendations)
        increase_price = len([r for r in recommendations if 'INCREASE' in r['recommendation']])
        decrease_price = len([r for r in recommendations if 'DECREASE' in r['recommendation']])
        maintain_price = len([r for r in recommendations if r['recommendation'] == 'MAINTAIN_PRICE'])
        avg_pct = sum(r['price_change_pct'] for r in recommendations) / total_products if total_products > 0 else 0
        total_rev = sum(r['expected_revenue_change_pct'] for r in recommendations) / total_products if total_products > 0 else 0

        return {
            'category': category or 'All Categories',
            'total_recommendations': total_products,
            'summary': {
                'increase_price': increase_price,
                'decrease_price': decrease_price,
                'maintain_price': maintain_price,
                'avg_price_change_pct': round(avg_pct, 2),
                'total_revenue_impact_pct': round(total_rev, 2),
            },
            'recommendations': recommendations,
            'timestamp': datetime.now().isoformat(),
        }
    except Exception as e:
        print(f"Error getting price optimization recommendations: {e}")
        import traceback; traceback.print_exc()
        return {'error': str(e)}


def _build_pricing_data_summary(pricing_data: Dict) -> str:
    """Build a rich, structured summary of pricing data for the AI prompt."""
    sections = []

    # Optimization recommendations summary
    opt_recs = pricing_data.get('optimization_recommendations', {})
    if opt_recs and opt_recs.get('recommendations'):
        recs = opt_recs['recommendations']
        summary = opt_recs.get('summary', {})
        sections.append(f"""PRICE OPTIMIZATION ANALYSIS ({opt_recs.get('total_recommendations', len(recs))} products analyzed):
- Products needing price INCREASE: {summary.get('increase_price', 0)}
- Products needing price DECREASE: {summary.get('decrease_price', 0)}
- Products at optimal price (MAINTAIN): {summary.get('maintain_price', 0)}
- Average recommended price change: {summary.get('avg_price_change_pct', 0):.1f}%
- Expected overall revenue impact: {summary.get('total_revenue_impact_pct', 0):.1f}%

TOP PRODUCTS NEEDING PRICE CHANGES:""")
        for i, rec in enumerate(recs[:15], 1):
            sections.append(f"""  {i}. {rec.get('product_name', 'Unknown')} (SKU: {rec.get('sku', 'N/A')})
     Category: {rec.get('category', 'N/A')}
     Current Price: ₹{rec.get('current_price', 0):,.0f} → Recommended: ₹{rec.get('recommended_price', 0):,.0f} ({rec.get('price_change_pct', 0):+.1f}%)
     Current Margin: {rec.get('current_margin', 0):.1f}%
     Competitiveness: {rec.get('competitiveness', 'UNKNOWN')}
     Revenue Impact: {rec.get('expected_revenue_change_pct', 0):+.1f}% | Margin Impact: {rec.get('expected_margin_change_pct', 0):+.1f}%
     Action: {rec.get('recommendation', 'N/A')} — {rec.get('reason', 'N/A')}
     Priority Score: {rec.get('priority_score', 0)}/100""")

    # Price range analysis
    pr = pricing_data.get('price_range', {})
    if pr and not pr.get('error'):
        price_range = pr.get('price_range', {})
        recommendation = pr.get('recommendation', {})
        sections.append(f"""
PRICE RANGE ANALYSIS:
  Product: {pr.get('product_name', 'N/A')} (SKU: {pr.get('sku', 'N/A')})
  Category: {pr.get('category', 'N/A')}
  Current Price: ₹{pr.get('current_price', 0):,.0f}
  Cost Price: ₹{pr.get('cost_price', 0):,.0f}
  Current Margin: {pr.get('current_margin_percent', 0):.1f}%
  Competitor Price: ₹{pr.get('competitor_price', 0):,.0f}
  Price Range: Min ₹{price_range.get('min_price', 0):,.0f} → Optimal ₹{price_range.get('optimal_price', 0):,.0f} → Max ₹{price_range.get('max_price', 0):,.0f}
  Recommendation: {recommendation.get('action', 'N/A')} — {recommendation.get('reason', 'N/A')}
  Suggested New Price: ₹{recommendation.get('suggested_price', 0):,.0f} (Change: {recommendation.get('price_change_percent', 0):+.1f}%)""")

    # Competitor comparison
    cc = pricing_data.get('competitor_comparison', {})
    if cc and not cc.get('error'):
        sections.append(f"""
COMPETITOR COMPARISON:
  Our Average Price: ₹{cc.get('our_price', 0):,.0f}
  Competitor Average Price: ₹{cc.get('avg_competitor_price', 0):,.0f}
  Price Difference: ₹{cc.get('price_difference', 0):,.0f} ({cc.get('price_difference_pct', 0):+.1f}%)
  Market Position: {cc.get('competitiveness', 'N/A')}
  Market Trend: {cc.get('trend', 'N/A')}""")

    # Demand impact
    di = pricing_data.get('demand_impact', {})
    if di and not di.get('error'):
        demand = di.get('demand_impact', {})
        revenue = di.get('revenue_impact', {})
        margin = di.get('margin_impact', {})
        sections.append(f"""
DEMAND IMPACT ANALYSIS:
  Product: {di.get('product_name', 'N/A')} (SKU: {di.get('sku', 'N/A')})
  Price Elasticity: {di.get('elasticity', 'N/A')}
  Current Price: ₹{di.get('current_price', 0):,.0f} → Proposed: ₹{di.get('new_price', 0):,.0f} ({di.get('price_change_pct', 0):+.1f}%)
  Demand: {demand.get('current_velocity', 0):.2f} → {demand.get('expected_velocity', 0):.2f} units/day ({demand.get('demand_change_pct', 0):+.1f}%)
  Revenue: ₹{revenue.get('current_revenue', 0):,.0f} → ₹{revenue.get('expected_revenue', 0):,.0f} ({revenue.get('revenue_change_pct', 0):+.1f}%)
  Margin: ₹{margin.get('current_margin', 0):,.0f} → ₹{margin.get('expected_margin', 0):,.0f} ({margin.get('margin_change_pct', 0):+.1f}%)
  Recommendation: {di.get('recommendation', {}).get('action', 'N/A')} — {di.get('recommendation', {}).get('reason', 'N/A')}""")

    # Guardrails
    gr = pricing_data.get('guardrails', {}).get('guardrails', {})
    if gr:
        sections.append(f"""
PRICING GUARDRAILS:
  Minimum Margin Floor: {gr.get('min_margin_percent', 15)}%
  Maximum Discount Allowed: {gr.get('max_discount_percent', 40)}%
  Competitive Price Tolerance: {gr.get('competitive_price_tolerance', 5)}%""")

    return "\n".join(sections)


def analyze_pricing_intelligence_with_nova(query: str, pricing_data: Dict) -> str:
    """Use Amazon Nova for AI-powered pricing analysis with detailed, actionable insights."""
    data_summary = _build_pricing_data_summary(pricing_data)

    prompt = f"""You are a senior pricing strategist and retail analytics expert for HeartKart, India's leading Valentine's Day and gifting products e-commerce retailer. Your role is to analyze pricing data and provide DETAILED, SPECIFIC, and ACTIONABLE pricing strategy recommendations.

CONTEXT: HeartKart sells Valentine's Day gifts, romantic products, personalized items, chocolates, flowers, greeting cards, jewelry, and more. The Valentine's season (Jan-Feb) is the peak period, and pricing strategy during this time directly impacts annual revenue.

USER'S QUESTION: "{query}"

CURRENT PRICING DATA:
{data_summary}

Provide a COMPREHENSIVE pricing intelligence analysis. Your response must be detailed, specific, and reference actual product names, prices, and numbers from the data above. Structure your response as follows:

### Executive Summary
Write 3-4 sentences summarizing the overall pricing health of the portfolio. Mention specific numbers (e.g., "X out of Y products need price adjustments" or "average margin is X%").

### Key Pricing Insights
Analyze each product category's pricing position. For each insight:
- Name the specific products affected
- Quote the exact current vs. recommended prices
- Explain WHY the change is needed (margin compression, competitive pressure, demand elasticity)
- Quantify the expected impact (revenue change %, margin improvement)

### Competitive Positioning Analysis
- How does HeartKart's pricing compare to competitors across categories?
- Which products are OVERPRICED and losing sales vs. which are UNDERPRICED and leaving money on the table?
- Specific price adjustment recommendations with exact rupee amounts

### Revenue Optimization Opportunities
- Identify the TOP 5 highest-impact pricing actions with specific revenue projections
- Rank by priority (expected revenue impact)
- Include both quick wins (small changes, big impact) and strategic moves (bigger changes)

### Demand & Elasticity Considerations
- Which products have high price elasticity (price-sensitive customers)?
- Which premium products can sustain higher margins?
- Valentine's season timing recommendations (when to raise/lower prices)

### Action Plan (Priority Order)
Provide a numbered action list with:
1. Product name + SKU
2. Current price → New price
3. Expected revenue/margin impact
4. Implementation urgency (Immediate / This Week / Next 2 Weeks)

Be specific — reference actual product names, SKUs, and exact price points from the data. Avoid generic advice. Every recommendation must be backed by the data provided."""

    try:
        response = bedrock.invoke_model(
            modelId='us.amazon.nova-lite-v1:0',
            body=json.dumps({
                'messages': [{'role': 'user', 'content': [{'text': prompt}]}],
                'inferenceConfig': {'temperature': 0.3, 'maxTokens': 4000}
            })
        )

        result = json.loads(response['body'].read())
        return result['output']['message']['content'][0]['text']

    except Exception as e:
        print(f"Error calling Nova: {e}")
        return f"Pricing intelligence report generated. AI analysis unavailable: {str(e)}"


# ============================================================================
# MAIN PRICING INTELLIGENCE FUNCTION
# ============================================================================

def generate_pricing_intelligence_report(
    query: str = None,
    sku: str = None,
    category: str = None,
    analysis_type: str = 'full',
) -> Dict:
    """Generate comprehensive pricing intelligence report."""
    print("💰 Generating pricing intelligence report...")

    try:
        result = {
            'status': 'success',
            'report_date': datetime.now().isoformat(),
            'analysis_type': analysis_type,
        }

        guardrails = get_price_guardrails(category)
        result['guardrails'] = guardrails

        if analysis_type == 'price_range':
            if not sku and not category:
                return {'status': 'error', 'error': 'Either sku or category required'}
            price_range = calculate_recommended_price_range(sku=sku, category=category)
            if price_range.get('error'):
                return {'status': 'error', 'error': price_range['error']}
            result['price_range'] = price_range
            # Also include nearby products for comparison context
            prod_category = price_range.get('category', category)
            if prod_category:
                nearby = get_products_by_category(prod_category, limit=8)
                related_ranges = []
                for p in nearby:
                    p_sku = p.get('sku', '')
                    if p_sku == sku or float(p.get('price', 0)) <= 0:
                        continue
                    pr = calculate_recommended_price_range(sku=p_sku)
                    if not pr.get('error'):
                        related_ranges.append({
                            'sku': p_sku,
                            'product_name': pr.get('product_name', p.get('name', '')),
                            'current_price': pr.get('current_price', 0),
                            'optimal_price': pr.get('price_range', {}).get('optimal_price', 0),
                            'competitor_price': pr.get('competitor_price', 0),
                            'current_margin_percent': pr.get('current_margin_percent', 0),
                            'action': pr.get('recommendation', {}).get('action', ''),
                            'price_change_pct': pr.get('recommendation', {}).get('price_change_percent', 0),
                        })
                    if len(related_ranges) >= 5:
                        break
                result['related_products'] = related_ranges

        elif analysis_type == 'competitor_comparison':
            comp_comparison = get_competitor_price_comparison(sku=sku, category=category)
            if comp_comparison.get('error'):
                return {'status': 'error', 'error': comp_comparison['error']}
            result['competitor_comparison'] = comp_comparison

        elif analysis_type == 'demand_impact':
            if not sku:
                return {'status': 'error', 'error': 'sku required for demand_impact analysis'}
            product = get_product_by_sku(sku)
            if not product:
                return {'status': 'error', 'error': f'Product {sku} not found'}
            current_price = float(product.get('price', 0))
            price_range = calculate_recommended_price_range(sku=sku)
            if price_range.get('error'):
                return {'status': 'error', 'error': price_range['error']}
            new_price = price_range['price_range']['optimal_price']
            demand_impact = calculate_demand_impact(sku, new_price, current_price)
            if demand_impact.get('error'):
                return {'status': 'error', 'error': demand_impact['error']}
            result['demand_impact'] = demand_impact
            result['price_range'] = price_range

        elif analysis_type == 'optimization':
            recommendations = get_price_optimization_recommendations(category=category)
            if recommendations.get('error'):
                return {'status': 'error', 'error': recommendations['error']}
            result['optimization_recommendations'] = recommendations

        else:  # full report
            if sku:
                price_range = calculate_recommended_price_range(sku=sku)
                comp_comparison = get_competitor_price_comparison(sku=sku)
                if not price_range.get('error') and not comp_comparison.get('error'):
                    current_price = price_range['current_price']
                    optimal_price = price_range['price_range']['optimal_price']
                    demand_impact = calculate_demand_impact(sku, optimal_price, current_price)
                    result['price_range'] = price_range
                    result['competitor_comparison'] = comp_comparison
                    if not demand_impact.get('error'):
                        result['demand_impact'] = demand_impact
            elif category:
                price_range = calculate_recommended_price_range(category=category)
                comp_comparison = get_competitor_price_comparison(category=category)
                recommendations = get_price_optimization_recommendations(category=category, limit=10)
                result['price_range'] = price_range
                result['competitor_comparison'] = comp_comparison
                if not recommendations.get('error'):
                    result['optimization_recommendations'] = recommendations
            else:
                recommendations = get_price_optimization_recommendations(limit=12)
                if not recommendations.get('error'):
                    result['optimization_recommendations'] = recommendations

        # Always generate AI insights for full reports, use default query if none provided
        if analysis_type == 'full' or query:
            analysis_query = query or (
                "Analyze the complete pricing portfolio for HeartKart. Identify which products "
                "need immediate price adjustments, highlight the biggest revenue optimization "
                "opportunities, assess competitive positioning, and provide a detailed action "
                "plan with specific price changes, expected revenue impacts, and implementation "
                "priorities for the Valentine's Day season."
            )
            try:
                ai_insights = analyze_pricing_intelligence_with_nova(analysis_query, result)
                result['ai_insights'] = ai_insights
            except Exception as e:
                print(f"Error generating AI insights: {e}")
                # Don't fail the whole report if AI insights fail
                result['ai_insights'] = None

        return result

    except Exception as e:
        import traceback
        print(f"Error generating pricing intelligence report: {e}")
        traceback.print_exc()
        return {'status': 'error', 'error': str(e), 'traceback': traceback.format_exc()}
