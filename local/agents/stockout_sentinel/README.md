# 🎯 Stockout Sentinel Agent

## Overview

The Stockout Sentinel predicts product stockouts and suggests intelligent substitutes to maintain customer satisfaction during the Valentine's shopping season.

## Key Features

### 1. 🔮 Stockout Prediction
- Calculates sales velocity from order history
- Predicts exact stockout dates
- Assigns risk levels (CRITICAL, HIGH, MEDIUM, LOW)
- Tracks days until stockout

### 2. 🔄 Intelligent Substitutes
- Finds alternatives based on:
  - **Category** (same type of product)
  - **Color** (matching or complementary)
  - **Price** (±30% range)
  - **Availability** (in stock)
  - **Popularity** (customer preferences)

### 3. 🤖 AI-Powered Insights
- Pattern analysis across categories
- Customer impact assessment
- Substitute strategy recommendations
- Preventive action suggestions

### 4. 📊 Comprehensive Reporting
- Category-wise breakdown
- Color distribution analysis
- Substitute coverage metrics
- Risk level summaries

## How It Works

### Stockout Prediction Algorithm

```python
days_until_stockout = current_stock / daily_sales_velocity

if days <= 3:  risk = CRITICAL
elif days <= 7:  risk = HIGH
elif days <= 14: risk = MEDIUM
else: risk = LOW
```

### Substitute Matching Algorithm

```python
match_score = (
    category_match * 0.4 +  # Same category is most important
    color_match * 0.3 +     # Color preference matters
    price_match * 0.3       # Price similarity
) * 100
```

## API Endpoints

### 1. Get Stockout Report
```bash
GET /api/stockout/report

Query Params:
- risk_level: CRITICAL | HIGH | MEDIUM | LOW
- category: Filter by category

Response:
{
  "status": "success",
  "summary": {
    "total_at_risk": 45,
    "critical_risk": 8,
    "high_risk": 15,
    "products_with_substitutes": 42,
    "substitute_coverage": 93.3
  },
  "at_risk_products": [...]
}
```

### 2. Get Substitutes for Product
```bash
GET /api/stockout/substitutes/<sku>

Response:
{
  "status": "success",
  "product": {
    "sku": "ORNAMENT-RED-BALL",
    "name": "Red Glass Ornament",
    "current_stock": 5,
    "stockout_prediction": {
      "days_until_stockout": 4,
      "stockout_date": "2025-11-20",
      "risk_level": "CRITICAL"
    }
  },
  "substitutes": [
    {
      "sku": "ORNAMENT-GOLD-BALL",
      "name": "Gold Glass Ornament",
      "price": 12.99,
      "match_score": 85.5,
      "reason": "Same category • Alternative color (gold) • Similar price"
    }
  ]
}
```

### 3. Get Critical Stockouts
```bash
GET /api/stockout/critical

Response:
{
  "status": "success",
  "count": 8,
  "critical_stockouts": [...]
}
```

### 4. Get Stockouts by Category
```bash
GET /api/stockout/by-category

Response:
{
  "status": "success",
  "categories": [
    {
      "category": "decorations",
      "total_products": 15,
      "critical_count": 3,
      "high_count": 7,
      "products": [...]
    }
  ]
}
```

### 5. Bulk Substitute Suggestions
```bash
POST /api/stockout/substitute-suggestions
Content-Type: application/json

{
  "skus": ["SKU1", "SKU2", "SKU3"]
}

Response:
{
  "status": "success",
  "count": 3,
  "substitutes": [...]
}
```

## Use Cases

### 1. Customer-Facing Scenarios

**Scenario: Red ornaments sold out**
```
Customer searches: "Red Valentine ornaments"
System detects: Out of stock
Sentinel suggests: 
  ✓ Gold ornaments (same category, alternative color)
  ✓ Silver ornaments (similar price, in stock)
  ✓ Red wreaths (same color, different category)
```

**Scenario: Premium tree unavailable**
```
Customer wants: $299 Premium Tree (7ft)
System detects: Only 2 left, stockout in 3 days
Sentinel suggests:
  ✓ $279 Deluxe Tree (7ft) - Similar, lower price
  ✓ $319 Premium Tree (9ft) - Larger, slightly more
  ✓ $289 Premium Tree (6ft) - Smaller, similar price
```

### 2. Internal Operations

**Inventory Management**
- Daily stockout risk reports
- Category-wise alerts
- Substitute coverage tracking
- Reorder priority lists

**Customer Service**
- Real-time substitute lookup
- Proactive customer communication
- Alternative product suggestions
- Backorder management

**Marketing**
- Promote substitute products
- Bundle recommendations
- Cross-sell opportunities
- Clearance strategies

## Example Output

### Stockout Report Summary
```
📊 SUMMARY
  Products at risk: 45
  Critical risk: 8
  High risk: 15
  Products with substitutes: 42
  Substitute coverage: 93.3%

🎨 Categories Affected:
    decorations: 18 products
    lights: 12 products
    trees: 8 products
    apparel: 7 products

🤖 AI ANALYSIS:
Critical patterns identified:
1. Red and gold decorations showing highest stockout risk
2. Premium price range ($50-$100) most affected
3. Outdoor decorations category needs immediate attention

Customer Impact:
- 8 products will stock out within 3 days
- High-demand items (ornaments, lights) at risk
- Substitute coverage is strong at 93%

Substitute Strategy:
- Promote gold/silver alternatives for red items
- Highlight similar-priced options
- Bundle slow-moving items with popular ones

Preventive Actions:
- Expedite reorders for critical items
- Increase safety stock for high-velocity products
- Monitor daily sales velocity during peak season
```

### Individual Product Analysis
```
🚨 Red Glass Ornament Ball (ORNAMENT-RED-BALL)
   Risk: CRITICAL | Stock: 5 units
   Stockout in: 4 days (2025-11-20)
   Velocity: 1.2/day

   💡 Substitutes (5):
      • Gold Glass Ornament Ball ($12.99) - 85.5% match
        Same category • Alternative color (gold) • Similar price
      
      • Silver Glass Ornament Ball ($11.99) - 82.3% match
        Same category • Alternative color (silver) • Lower price ($1.00 less)
      
      • Red Glitter Ornament ($14.99) - 78.9% match
        Same category • Same color (red) • Premium option ($2.00 more)
```

## Integration Examples

### Frontend Integration
```typescript
// Check if product has substitutes
const checkSubstitutes = async (sku: string) => {
  const response = await fetch(`/api/stockout/substitutes/${sku}`)
  const data = await response.json()
  
  if (data.status === 'success' && data.substitutes.length > 0) {
    showSubstituteModal(data.substitutes)
  }
}

// Show substitute suggestions
const showSubstituteModal = (substitutes) => {
  return (
    <div>
      <h3>This item is running low! Consider these alternatives:</h3>
      {substitutes.map(sub => (
        <div key={sub.sku}>
          <h4>{sub.name} - ${sub.price}</h4>
          <p>{sub.reason}</p>
          <span>{sub.match_score}% match</span>
        </div>
      ))}
    </div>
  )
}
```

### Email Notifications
```python
# Send stockout alerts
def send_stockout_alerts():
    report = generate_stockout_report()
    critical = [p for p in report['at_risk_products'] 
                if p['risk_level'] == 'CRITICAL']
    
    for product in critical:
        send_email(
            to='inventory@heartkart.com',
            subject=f'CRITICAL: {product["name"]} stocks out in {product["days_until_stockout"]} days',
            body=f'''
            Product: {product["name"]}
            Current Stock: {product["current_stock"]}
            Stockout Date: {product["stockout_date"]}
            
            Substitutes Available: {len(product["substitutes"])}
            '''
        )
```

## Running the Agent

### CLI Mode
```bash
cd agents/stockout_sentinel
python3 stockout_sentinel_agent.py
```

### API Mode
```bash
cd agents/stockout_sentinel
python3 stockout_api.py
# Server runs on http://localhost:5002
```

### Test Specific Product
```python
from stockout_sentinel_agent import get_substitute_for_product

result = get_substitute_for_product('ORNAMENT-RED-BALL')
print(result)
```

## Configuration

### Adjust Risk Thresholds
```python
# In stockout_sentinel_agent.py
if days_until_stockout <= 3:  # Change to 5 for more aggressive
    risk_level = 'CRITICAL'
```

### Adjust Substitute Matching
```python
# Price range tolerance
min_price = price * 0.7  # Change to 0.5 for wider range
max_price = price * 1.3  # Change to 1.5 for wider range

# Match score weights
overall_match = (
    category_match * 0.4 +  # Increase for stricter category matching
    color_match * 0.3 +     # Increase for stricter color matching
    price_match * 0.3       # Increase for stricter price matching
)
```

## Benefits

### For Customers
- ✅ Never leave empty-handed
- ✅ Discover similar products
- ✅ Find better deals
- ✅ Save time searching

### For Business
- ✅ Reduce lost sales
- ✅ Improve customer satisfaction
- ✅ Optimize inventory
- ✅ Increase cross-sell opportunities

### For Operations
- ✅ Proactive stockout prevention
- ✅ Data-driven reordering
- ✅ Category insights
- ✅ Automated recommendations

## Future Enhancements

1. **Machine Learning**
   - Learn customer preferences
   - Predict seasonal patterns
   - Optimize substitute rankings

2. **Real-Time Alerts**
   - WebSocket notifications
   - SMS/Email alerts
   - Dashboard widgets

3. **Advanced Matching**
   - Image similarity
   - Customer review sentiment
   - Bundle recommendations

4. **Integration**
   - E-commerce platform hooks
   - CRM integration
   - Marketing automation

## Performance

- **Report Generation**: ~2-3 seconds for 200 products
- **Substitute Lookup**: ~100ms per product
- **AI Analysis**: ~1-2 seconds
- **API Response Time**: < 500ms average

## Dependencies

- boto3 (AWS SDK)
- opensearchpy (Search)
- flask (API)
- flask-cors (CORS support)

## Summary

The Stockout Sentinel is a critical agent for maintaining customer satisfaction during peak shopping seasons. By predicting stockouts and suggesting intelligent alternatives, it helps prevent lost sales while improving the shopping experience.

**Perfect for Valentine's shopping where:**
- Inventory moves fast
- Customer expectations are high
- Product variety is important
- Substitutes can save the sale
