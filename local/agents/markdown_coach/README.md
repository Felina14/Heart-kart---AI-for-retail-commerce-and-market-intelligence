# 🏷️ Markdown & Clearance Coach Agent

AI-powered pricing strategist that identifies aged inventory and recommends optimal markdown strategies to maximize revenue recovery.

## 🎯 Purpose

Post-holiday and seasonal clearance is critical for:
- Recovering capital from slow-moving inventory
- Freeing warehouse space for new products
- Preventing inventory obsolescence
- Optimizing cash flow

## 🔥 Key Features

### 1. **Aged Inventory Detection**
- Identifies products with >60 days of inventory
- Categorizes by urgency: DEAD_STOCK, CRITICAL, HIGH, MEDIUM
- Calculates days of inventory remaining
- Tracks sales velocity trends

### 2. **Smart Markdown Recommendations**
- **Dead Stock (0 sales)**: 50% off - aggressive clearance
- **Critical (>180 days)**: 35% off - deep discount
- **High (>120 days)**: 25% off - significant markdown
- **Medium (>60 days)**: 15% off - gentle acceleration

### 3. **AI-Powered Clearance Planning**
- Overall clearance strategy (timing, channels)
- Category-specific recommendations
- Risk assessment and alternatives
- Donation/liquidation suggestions

### 4. **Phased Timeline**
- **Immediate**: Dead stock & critical items
- **Week 2**: High-priority items if not sold
- **Week 4**: Final clearance phase
- **Liquidation**: Send to liquidator if unsold

### 5. **Bundle Suggestions**
- Creates category-based bundles
- 30% off bundle pricing
- Moves multiple aged items together
- "Clearance Bundle" packages

## 📊 How It Works

```python
from markdown_coach_agent import MarkdownCoachAgent

agent = MarkdownCoachAgent()

# 1. Analyze aged inventory
aged_products = agent.analyze_aged_inventory(age_threshold_days=60)

# 2. Generate clearance plan
clearance_plan = agent.generate_clearance_plan(aged_products)

# 3. Get phased timeline
timeline = agent.get_clearance_timeline(aged_products)

# 4. Suggest bundles
bundles = agent.suggest_bundles(aged_products)
```

## 🎨 Example Output

```json
{
  "summary": {
    "total_aged_items": 45,
    "total_aged_value": 12450.00,
    "potential_revenue": 9337.50,
    "recovery_rate": 75.0
  },
  "aged_products": [
    {
      "sku": "SKU-001",
      "name": "Red Dinner Plate Set",
      "category": "Dinnerware",
      "current_price": 45.00,
      "quantity": 25,
      "sales_velocity": 0.1,
      "days_remaining": 250.0,
      "age_category": "CRITICAL",
      "markdown_recommendation": {
        "markdown_percentage": 35,
        "new_price": 29.25,
        "potential_revenue": 731.25,
        "reason": "Critical aging - deep discount to move quickly",
        "urgency": "HIGH"
      }
    }
  ],
  "timeline": {
    "immediate": [...],
    "week_2": [...],
    "week_4": [...],
    "liquidation": [...]
  },
  "suggested_bundles": [
    {
      "bundle_name": "Dinnerware Clearance Bundle",
      "items": [...],
      "regular_value": 225.00,
      "bundle_price": 157.50,
      "savings": 67.50,
      "savings_percentage": 30
    }
  ]
}
```

## 🚀 API Integration

Add to `app.py`:

```python
from agents.markdown_coach.markdown_coach_agent import generate_markdown_report

@app.route('/api/markdown/report', methods=['GET'])
def get_markdown_report():
    """Get markdown and clearance recommendations"""
    report = generate_markdown_report()
    return jsonify(report)

@app.route('/api/markdown/aged-inventory', methods=['GET'])
def get_aged_inventory():
    """Get list of aged inventory items"""
    agent = MarkdownCoachAgent()
    threshold = int(request.args.get('threshold', 60))
    aged = agent.analyze_aged_inventory(age_threshold_days=threshold)
    return jsonify({'status': 'success', 'aged_products': aged})
```

## 📈 Business Impact

### Revenue Recovery
- Typical recovery rate: 70-80% of aged inventory value
- Better than liquidation (30-40% recovery)
- Faster than waiting for organic sales

### Cash Flow
- Converts aged inventory to cash
- Frees capital for new products
- Reduces carrying costs

### Warehouse Efficiency
- Clears space for new inventory
- Reduces handling costs
- Improves inventory turnover

## 🎯 Use Cases

### 1. Post-Holiday Clearance
```python
# Post-season clearance after Valentine's Day
report = generate_markdown_report()
immediate_items = report['timeline']['immediate']
# Apply markdowns to these items first
```

### 2. Seasonal Transitions
```python
# Clear summer items before fall
aged = agent.analyze_aged_inventory(age_threshold_days=45)
# More aggressive threshold for seasonal items
```

### 3. Category Refresh
```python
# Clear old dinnerware before new collection
clearance_plan = agent.generate_clearance_plan(aged_products)
# Focus on specific category
```

### 4. Bundle Creation
```python
# Create themed bundles
bundles = agent.suggest_bundles(aged_products)
# "Holiday Clearance Bundle" at 30% off
```

## 🧠 AI Recommendations

The agent uses Amazon Nova to provide:
- Strategic timing advice
- Channel recommendations (online, in-store, email)
- Risk mitigation strategies
- Alternative options (donations, liquidation)

Example AI output:
```
CLEARANCE STRATEGY:
1. Start with 35% off on critical items immediately
2. Promote bundles via email campaign
3. If unsold after 2 weeks, increase to 50% off
4. Consider donation for tax benefits on remaining items

CATEGORY INSIGHTS:
- Dinnerware: High competition, price-sensitive
- Glassware: Bundle with dinnerware for better movement
- Decor: Seasonal, donate if unsold by February

RISK MITIGATION:
- Set aside 10% for liquidation
- Track markdown effectiveness weekly
- Adjust pricing based on sell-through rate
```

## 📊 Metrics to Track

- **Sell-through rate**: % of marked-down items sold
- **Revenue recovery**: Actual vs. potential revenue
- **Time to clear**: Days to sell marked-down inventory
- **Markdown effectiveness**: Sales lift after markdown

## 🔧 Configuration

Adjust thresholds in the agent:

```python
# More aggressive for seasonal items
aged = agent.analyze_aged_inventory(age_threshold_days=45)

# More conservative for evergreen items
aged = agent.analyze_aged_inventory(age_threshold_days=90)
```

## 🎨 Frontend Integration

Add a "Markdown Coach" tab to the dashboard showing:
- Aged inventory summary
- Markdown recommendations
- Clearance timeline
- Suggested bundles
- AI strategic advice

## 💡 Pro Tips

1. **Start Early**: Begin markdowns before items become dead stock
2. **Test & Learn**: Track which markdown percentages work best
3. **Bundle Smart**: Combine slow movers with popular items
4. **Communicate**: Email customers about clearance sales
5. **Set Limits**: Don't markdown below cost unless necessary

## 🚨 When to Use

- ✅ Post-holiday clearance (January)
- ✅ Seasonal transitions (end of summer/winter)
- ✅ Before new product launches
- ✅ When warehouse space is tight
- ✅ To improve cash flow

## 📝 Notes

- Markdown percentages are recommendations, not rules
- Consider brand positioning when setting prices
- Track competitor pricing during clearance
- Some items may be better donated for tax benefits
- Liquidators typically pay 30-40% of wholesale value

---

**Built with:** Amazon Bedrock (Nova), OpenSearch, Python
**Status:** Ready for production
**Impact:** High - Direct revenue recovery
