# 🔍 Exception Investigator Agent

Detects anomalies in sales patterns and inventory behavior using statistical analysis and AI insights.

## What It Does

The Exception Investigator monitors your inventory for unusual patterns:

- **Demand Surges**: Products selling much faster than normal
- **Demand Drops**: Products with sudden sales decline
- **Stagnant Inventory**: Items with no sales for extended periods

## How It Works

### 1. Data Collection
- Fetches sales data from DynamoDB (last 30 days)
- Aggregates by SKU and date
- Calculates daily sales patterns

### 2. Statistical Analysis
- Calculates mean and standard deviation for each product
- Compares recent sales (last 3 days) to historical average
- Uses Z-score to detect anomalies (default threshold: 2.0)

### 3. Anomaly Classification

**Demand Surge** (Z-score > 2.0)
- Recent sales significantly higher than average
- Severity: HIGH (Z > 3.0) or MEDIUM (Z > 2.0)
- Risk: Potential stockout

**Demand Drop** (Z-score < -2.0)
- Recent sales significantly lower than average
- Severity: HIGH (Z < -3.0) or MEDIUM (Z < -2.0)
- Risk: Overstock, market shift

**Stagnant** (No sales in 7 days)
- Zero sales for a week
- Severity: MEDIUM
- Risk: Dead inventory

### 4. AI Insights
- Amazon Nova analyzes patterns
- Provides actionable recommendations
- Identifies risks and opportunities

## Usage

### Python
```python
from exception_investigator_agent import investigate_exceptions

# Run investigation
result = investigate_exceptions(days=30, threshold=2.0)

print(f"Found {result['summary']['total_anomalies']} anomalies")
print(result['insights'])

for anomaly in result['anomalies']:
    print(f"{anomaly['name']}: {anomaly['anomaly_type']}")
```

### API
```bash
# Get all anomalies
curl http://localhost:5000/api/exceptions/investigate

# Custom parameters
curl "http://localhost:5000/api/exceptions/investigate?days=14&threshold=2.5"

# Get summary only
curl http://localhost:5000/api/exceptions/summary
```

## Response Format

```json
{
  "status": "success",
  "summary": {
    "total_anomalies": 15,
    "by_type": {
      "DEMAND_SURGE": 8,
      "DEMAND_DROP": 5,
      "STAGNANT": 2
    },
    "by_severity": {
      "HIGH": 3,
      "MEDIUM": 12
    },
    "date_range_days": 30,
    "total_orders_analyzed": 89
  },
  "anomalies": [
    {
      "sku": "BALLOON-LATEX-RED-50PK",
      "name": "Red Latex Balloons (50 pack)",
      "anomaly_type": "DEMAND_SURGE",
      "severity": "HIGH",
      "z_score": 3.45,
      "recent_avg_daily": 2.33,
      "historical_avg_daily": 0.5,
      "total_sales": 7,
      "stock_quantity": 77,
      "price": 12.99,
      "category": "party-decorations",
      "vendor_name": "Holiday Decor Wholesale"
    }
  ],
  "insights": "AI-generated analysis and recommendations...",
  "generated_at": "2025-11-16T02:30:00"
}
```

## Configuration

### Threshold Tuning
- **2.0** (default): Moderate sensitivity, catches significant anomalies
- **1.5**: Higher sensitivity, more alerts
- **3.0**: Lower sensitivity, only extreme anomalies

### Time Window
- **30 days** (default): Good balance for seasonal business
- **14 days**: More responsive to recent changes
- **60 days**: Longer-term pattern analysis

## Use Cases

### 1. Daily Monitoring
```python
# Check for new anomalies daily
result = investigate_exceptions(days=7, threshold=2.0)
if result['summary']['by_severity'].get('HIGH', 0) > 0:
    send_alert(result)
```

### 2. Stockout Prevention
```python
# Focus on demand surges
surges = [a for a in result['anomalies'] if a['anomaly_type'] == 'DEMAND_SURGE']
for surge in surges:
    if surge['stock_quantity'] < 20:
        trigger_emergency_reorder(surge['sku'])
```

### 3. Clearance Planning
```python
# Find stagnant inventory
stagnant = [a for a in result['anomalies'] if a['anomaly_type'] == 'STAGNANT']
for item in stagnant:
    suggest_markdown(item['sku'], discount=0.25)
```

## Data Requirements

- **Minimum**: 3 days of sales data per SKU
- **Recommended**: 30+ days for accurate baselines
- **Optimal**: Full seasonal cycle (90+ days)

## Limitations

- Requires historical data (won't work on day 1)
- Seasonal products may show false positives
- New products lack baseline data
- Low-volume items may have noisy signals

## Integration

Works seamlessly with other agents:
- **Replenishment Planner**: Prioritize anomalies in reorder calculations
- **Stockout Sentinel**: Cross-reference surge alerts with stockout risks
- **Inventory Copilot**: Query anomalies via natural language

## Technical Details

### Statistical Method
- **Z-Score**: (recent_avg - historical_mean) / std_dev
- **Threshold**: Number of standard deviations from mean
- **Window**: Last 3 days vs. full historical period

### Performance
- Analyzes 1,500+ SKUs in ~5 seconds
- Caches results for 1 hour
- Scales to 10,000+ SKUs

## Example Output

```
🔍 EXCEPTION INVESTIGATOR - Anomaly Detection
======================================================================

📊 Summary:
  Total Anomalies: 15
  By Type: {'DEMAND_SURGE': 8, 'DEMAND_DROP': 5, 'STAGNANT': 2}
  By Severity: {'HIGH': 3, 'MEDIUM': 12}

💡 Insights:
You have 8 products experiencing demand surges, with 3 at HIGH severity.
Key findings:
1. Red Latex Balloons - 365% increase in daily sales (Z=3.45)
2. Santa Foil Balloons - 280% increase (Z=2.89)
3. Happy Holidays Banner - 250% increase (Z=2.67)

Recommendations:
- Expedite reorders for high-surge items with low stock
- Monitor surge products for potential stockouts
- Investigate demand drops for seasonal timing issues

Risk Assessment:
- 3 products at risk of stockout within 7 days
- 2 stagnant items should be considered for clearance
```

## Next Steps

1. **Set up daily monitoring** - Run investigation every morning
2. **Configure alerts** - Email/Slack for HIGH severity anomalies
3. **Integrate with Replenishment** - Auto-adjust reorder quantities
4. **Track accuracy** - Monitor false positive rate over time
