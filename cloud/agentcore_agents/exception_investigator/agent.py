"""
Exception Investigator Agent for AWS Bedrock AgentCore Runtime (Strands Framework)

AI-powered anomaly detection agent that analyzes real sales history data to identify
unusual trends, demand surges, and potential issues.
Uses the Strands framework with @tool decorators for all data access operations.
"""

import json
import os
import sys
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Any
from decimal import Decimal
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
bedrock = boto3.client('bedrock-runtime', region_name=REGION)

sales_table = dynamodb.Table('SalesHistory')

# Import product data access layer (local copy for Docker container)
from product_data_access import get_all_products, get_product_by_sku


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

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


def get_sales_data(days: int = 30) -> Dict:
    """Get sales data from DynamoDB SalesHistory table."""
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    try:
        records = _scan_all(
            sales_table,
            FilterExpression=Attr('date').gte(cutoff_date)
        )

        sales_by_sku = {}
        for record in records:
            sku = record.get('sku', '')
            date_str = record.get('date', '')
            quantity = _to_num(record.get('quantity', 0))

            if sku not in sales_by_sku:
                sales_by_sku[sku] = {'total': 0, 'orders': 0, 'daily': {}}

            sales_by_sku[sku]['total'] += quantity
            sales_by_sku[sku]['orders'] += 1
            sales_by_sku[sku]['daily'][date_str] = (
                sales_by_sku[sku]['daily'].get(date_str, 0) + quantity
            )

        return {
            'sales_by_sku': sales_by_sku,
            'total_orders': len(records),
            'date_range_days': days,
        }

    except Exception as e:
        print(f"Error fetching sales data: {e}")
        return {'sales_by_sku': {}, 'total_orders': 0, 'date_range_days': days}


def detect_anomalies(sales_data: Dict, threshold: float = 1.5) -> List[Dict]:
    """
    Detect anomalies using comparison of recent vs historical averages.
    threshold: multiplier for detecting significant changes
    """
    anomalies = []
    sales_by_sku = sales_data['sales_by_sku']

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=sales_data['date_range_days'])

    for sku, data in sales_by_sku.items():
        if len(data['daily']) < 5:
            continue

        all_dates = [(start_date + timedelta(days=i)).isoformat() for i in range(sales_data['date_range_days'])]
        daily_sales = {date: data['daily'].get(date, 0) for date in all_dates}
        sorted_dates = sorted(daily_sales.keys())

        split_point = int(len(sorted_dates) * 0.8)
        historical_dates = sorted_dates[:split_point]
        recent_dates = sorted_dates[split_point:]

        historical_sales = [daily_sales[d] for d in historical_dates]
        recent_sales = [daily_sales[d] for d in recent_dates]

        historical_avg = sum(historical_sales) / len(historical_sales) if historical_sales else 0
        recent_avg = sum(recent_sales) / len(recent_sales) if recent_sales else 0

        std_dev = statistics.stdev(historical_sales) if len(historical_sales) > 1 else 1

        if std_dev > 0:
            z_score = (recent_avg - historical_avg) / std_dev
        else:
            z_score = 0

        anomaly_type = None
        severity = None

        if historical_avg > 0 and recent_avg > historical_avg * threshold:
            anomaly_type = 'DEMAND_SURGE'
            severity = 'HIGH' if z_score > 3 else 'MEDIUM'
        elif historical_avg > 0 and recent_avg == 0:
            anomaly_type = 'STAGNANT'
            severity = 'MEDIUM'
        elif historical_avg > 0 and recent_avg > 0 and recent_avg < historical_avg / threshold:
            anomaly_type = 'DEMAND_DROP'
            severity = 'MEDIUM'

        if anomaly_type:
            anomalies.append({
                'sku': sku,
                'anomaly_type': anomaly_type,
                'severity': severity,
                'z_score': round(z_score, 2),
                'recent_avg_daily': round(recent_avg, 2),
                'historical_avg_daily': round(historical_avg, 2),
                'total_sales': data['total'],
                'total_orders': data['orders'],
                'daily_sales': {k: v for k, v in daily_sales.items() if v > 0},
            })

    return sorted(anomalies, key=lambda x: abs(x['z_score']), reverse=True)


def enrich_with_product_data(anomalies: List[Dict]) -> List[Dict]:
    """Add product details from DynamoDB Products table."""
    enriched = []

    for anomaly in anomalies:
        try:
            product = get_product_by_sku(anomaly['sku'])
            if product:
                anomaly.update({
                    'name': product.get('name', 'Unknown'),
                    'category': product.get('category', 'Unknown'),
                    'price': float(product.get('price', 0)),
                    'stock_quantity': int(product.get('stock_quantity', product.get('inventory', 0))),
                    'vendor_name': product.get('vendor_name', 'Unknown'),
                })
            else:
                print(f"⚠️  SKU {anomaly['sku']} not found in Products table — including with placeholder data")
                anomaly.setdefault('name', f'Product {anomaly["sku"]}')
                anomaly.setdefault('category', 'Unknown')
                anomaly.setdefault('price', 0.0)
                anomaly.setdefault('stock_quantity', 0)
                anomaly.setdefault('vendor_name', 'Unknown')
        except Exception as e:
            print(f"❌ Error enriching SKU {anomaly['sku']}: {e} — including with placeholder data")
            anomaly.setdefault('name', f'Product {anomaly["sku"]}')
            anomaly.setdefault('category', 'Unknown')
            anomaly.setdefault('price', 0.0)
            anomaly.setdefault('stock_quantity', 0)
            anomaly.setdefault('vendor_name', 'Unknown')

        enriched.append(anomaly)

    print(f"✅ Enriched {len(enriched)} out of {len(anomalies)} anomalies")
    return enriched


def generate_insights(anomalies: List[Dict]) -> str:
    """Use Amazon Nova to generate insights about anomalies."""
    if not anomalies:
        return "No significant anomalies detected. Sales patterns are within normal ranges."

    summary = {
        'total_anomalies': len(anomalies),
        'by_type': {},
        'by_severity': {},
        'top_anomalies': anomalies[:10],
    }

    for anomaly in anomalies:
        atype = anomaly['anomaly_type']
        severity = anomaly['severity']
        summary['by_type'][atype] = summary['by_type'].get(atype, 0) + 1
        summary['by_severity'][severity] = summary['by_severity'].get(severity, 0) + 1

    prompt = f"""You are an inventory analyst. Analyze these sales anomalies and provide clear, actionable insights.

Anomaly Summary:
{json.dumps(summary, indent=2)}

Format your response EXACTLY like this (use simple markdown):

### **Overview**
[2-3 sentences about what's happening overall]

### **Key Findings**
1. **[Product Name]**: [Brief insight about the anomaly]
2. **[Product Name]**: [Brief insight about the anomaly]
3. **[Product Name]**: [Brief insight about the anomaly]

### **Recommendations**
- [Specific action 1]
- [Specific action 2]
- [Specific action 3]

### **Risk Assessment**
[2-3 sentences about potential risks and urgency]

Keep it concise and actionable. Focus on business impact. Do NOT use nested bullets or complex formatting."""

    try:
        response = bedrock.invoke_model(
            modelId='us.amazon.nova-lite-v1:0',
            body=json.dumps({
                'messages': [{'role': 'user', 'content': [{'text': prompt}]}],
                'inferenceConfig': {'temperature': 0.3, 'maxTokens': 1500},
            })
        )
        result = json.loads(response['body'].read())
        return result['output']['message']['content'][0]['text']
    except Exception as e:
        return f"Error generating insights: {e}"


# ============================================================================
# STRANDS TOOLS
# ============================================================================

@tool
def get_inventory_anomalies(days: int = 30, threshold: float = 2.0) -> Dict:
    """
    Detect inventory and demand anomalies by analyzing real sales history data from DynamoDB.

    Args:
        days: Analysis window in days (default: 30)
        threshold: Multiplier for detecting significant changes (default: 2.0)

    Returns:
        Dict with anomalies list (each with sku, name, anomaly_type, severity,
        z_score, recent_avg_daily, historical_avg_daily), summary counts, and generated_at.
    """
    try:
        sales_data = get_sales_data(days)

        if sales_data['total_orders'] == 0:
            return {
                'anomalies': [],
                'summary': {
                    'total_anomalies': 0,
                    'by_type': {},
                    'by_severity': {},
                    'date_range_days': days,
                    'total_orders_analyzed': 0,
                },
                'generated_at': datetime.now().isoformat(),
            }

        print(f"📊 Processing {sales_data['total_orders']} sales records...")

        anomalies = detect_anomalies(sales_data, threshold)
        enriched_anomalies = enrich_with_product_data(anomalies)

        by_type: Dict[str, int] = defaultdict(int)
        by_severity: Dict[str, int] = defaultdict(int)
        for a in enriched_anomalies:
            by_type[a['anomaly_type']] += 1
            by_severity[a['severity']] += 1

        return {
            'anomalies': enriched_anomalies,
            'summary': {
                'total_anomalies': len(enriched_anomalies),
                'by_type': dict(by_type),
                'by_severity': dict(by_severity),
                'date_range_days': days,
                'total_orders_analyzed': sales_data['total_orders'],
            },
            'generated_at': datetime.now().isoformat(),
        }

    except Exception as e:
        import traceback
        print(f"Error detecting anomalies: {e}")
        traceback.print_exc()
        return {
            'anomalies': [],
            'summary': {
                'total_anomalies': 0, 'by_type': {}, 'by_severity': {},
                'date_range_days': days, 'total_orders_analyzed': 0,
            },
            'generated_at': datetime.now().isoformat(),
            'error': str(e),
        }


@tool
def get_exception_product_details(sku: str) -> Dict:
    """
    Get detailed product information for an exception/anomaly investigation.

    Args:
        sku: Product SKU to investigate

    Returns:
        Full product details including stock levels, pricing, and vendor info.
    """
    try:
        product = get_product_by_sku(sku)
        if not product:
            return {'error': f'Product {sku} not found'}

        stock = int(product.get('stock_quantity', product.get('inventory', 0)))
        velocity = float(product.get('sales_velocity', 0))

        return {
            'sku': sku,
            'name': product.get('name', ''),
            'category': product.get('category', ''),
            'price': float(product.get('price', 0)),
            'stock_quantity': stock,
            'sales_velocity': velocity,
            'vendor_name': product.get('vendor_name', ''),
            'days_of_supply': round(stock / velocity, 1) if velocity > 0 else 999,
        }
    except Exception as e:
        print(f"Error getting product details for {sku}: {e}")
        return {'error': str(e)}


# ============================================================================
# STRANDS AGENT
# ============================================================================

bedrock_model = BedrockModel(
    model_id=os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
    temperature=float(os.getenv("MODEL_TEMPERATURE", "0.3")),
)

agent = Agent(
    model=bedrock_model,
    tools=[get_inventory_anomalies, get_exception_product_details],
    system_prompt=(
        "You are the HeartKart Exception Investigator Agent. Detect and analyze inventory anomalies "
        "that could impact Valentine's Day sales performance.\n\n"
        "Use your tools to:\n"
        "1. Detect anomalies using get_inventory_anomalies\n"
        "2. Investigate specific products using get_exception_product_details\n\n"
        "Format your analysis as:\n"
        "### Overview\n"
        "[Summary of what anomalies were found]\n\n"
        "### Key Findings\n"
        "1. [Product]: [Insight about the anomaly]\n"
        "2. [Product]: [Insight about the anomaly]\n\n"
        "### Recommendations\n"
        "- [Specific action items]\n\n"
        "### Risk Assessment\n"
        "[Business impact and urgency]\n\n"
        "Be concise and actionable. Focus on Valentine's Day business impact."
    ),
)


# ============================================================================
# CORE INVESTIGATION (structured output)
# ============================================================================

def investigate_exceptions(days: int = 30, threshold: float = 2.0) -> Dict:
    """Investigate exceptions using real SalesHistory data with statistical anomaly detection."""
    print(f"🔍 Investigating exceptions over last {days} days...")

    sales_data = get_sales_data(days)

    if sales_data['total_orders'] == 0:
        return {
            'status': 'success',
            'message': 'No sales data available for analysis',
            'anomalies': [],
            'summary': {
                'total_anomalies': 0,
                'by_type': {},
                'by_severity': {},
                'date_range_days': days,
                'total_orders_analyzed': 0,
            },
            'insights': 'Insufficient data for anomaly detection.',
            'generated_at': datetime.now().isoformat(),
        }

    print(f"📊 Analyzed {sales_data['total_orders']} orders")

    anomalies = detect_anomalies(sales_data, threshold)
    print(f"🚨 Found {len(anomalies)} anomalies")

    enriched_anomalies = enrich_with_product_data(anomalies)

    insights = generate_insights(enriched_anomalies)

    summary = {
        'total_anomalies': len(enriched_anomalies),
        'by_type': {},
        'by_severity': {},
        'date_range_days': days,
        'total_orders_analyzed': sales_data['total_orders'],
    }

    for anomaly in enriched_anomalies:
        atype = anomaly['anomaly_type']
        severity = anomaly['severity']
        summary['by_type'][atype] = summary['by_type'].get(atype, 0) + 1
        summary['by_severity'][severity] = summary['by_severity'].get(severity, 0) + 1

    return {
        'status': 'success',
        'anomalies': enriched_anomalies,
        'summary': summary,
        'insights': insights,
        'generated_at': datetime.now().isoformat(),
    }


# ============================================================================
# AGENTCORE RUNTIME ENTRY POINT
# ============================================================================

@app.entrypoint
def exception_investigator_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    AgentCore Runtime entry point for the Exception Investigator Agent.

    Args:
        payload: Input with optional 'days' (int) and 'threshold' (float) parameters

    Returns:
        Dictionary with anomaly analysis and AI-generated insights
    """
    print(f"Received request: {json.dumps(payload, default=str)}")

    try:
        days = payload.get('days', 30)
        threshold = payload.get('threshold', 2.0)

        result = investigate_exceptions(days=days, threshold=threshold)
        print(f"Generated result with {result['summary'].get('total_anomalies', 0)} anomalies")
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
