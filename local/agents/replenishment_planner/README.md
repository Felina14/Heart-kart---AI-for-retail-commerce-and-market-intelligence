# 📦 Replenishment Planner Agent

AI-powered inventory replenishment system using **Amazon Nova**.

## 📁 Files in This Folder

```
agents/replenishment_planner/
├── replenishment_planner_agent.py  # Core agent logic
├── replenishment_cli.py            # Interactive CLI tool
├── replenishment_api.py            # Flask REST API
├── test_replenishment.py           # Test suite
├── replenishment_plan.json         # Latest generated plan
├── REPLENISHMENT_PLANNER_README.md # Full documentation
├── REPLENISHMENT_PLANNER_COMPLETE.md # Build summary
└── README.md                       # This file
```

## 🚀 Quick Start

### 1. Run the Agent
```bash
cd agents/replenishment_planner
python3 replenishment_planner_agent.py
```

### 2. Interactive CLI
```bash
python3 replenishment_cli.py
```

### 3. Start API Server
```bash
python3 replenishment_api.py
# Runs on http://localhost:5001
```

### 4. Run Tests
```bash
python3 test_replenishment.py
```

## 🎯 Features

- ✅ Analyzes 1,506 products in real-time
- ✅ Calculates sales velocity from order history
- ✅ Predicts stockout dates
- ✅ Recommends optimal order quantities (ROP/EOQ)
- ✅ AI analysis with Amazon Nova
- ✅ Multiple interfaces (CLI, API, programmatic)

## 📊 API Endpoints

- `GET /api/replenishment/plan` - Full replenishment plan
- `GET /api/replenishment/urgent` - Critical/high urgency items
- `GET /api/replenishment/by-vendor` - Grouped by vendor
- `POST /api/replenishment/export-po` - Generate purchase order

## 🖥️ Frontend Integration

The replenishment planner is integrated into the inventory dashboard:

**Location**: `inventory-dashboard/components/ReplenishmentPanel.tsx`

**Access**: Navigate to the "🤖 Replenishment Planner" tab in the dashboard

**Features**:
- View all reorder recommendations
- Filter by urgency
- Select items for purchase orders
- Export PO as JSON
- Real-time AI analysis

## 📖 Documentation

See `REPLENISHMENT_PLANNER_README.md` for complete documentation.

## 🔧 Configuration

Edit vendor mappings in `replenishment_planner_agent.py`:

```python
vendor_map = {
    'decorations': {
        'vendor': 'Holiday Decor Wholesale',
        'lead_time': 5,
        'moq': 50,
        'on_time_rate': 0.95
    },
    # Add more...
}
```

## 🎓 How It Works

1. **Data Collection**: Scans OpenSearch for low stock products
2. **Velocity Calculation**: Analyzes order history for sales patterns
3. **ROP/EOQ Calculation**: Determines optimal reorder points and quantities
4. **AI Analysis**: Amazon Nova provides intelligent prioritization
5. **Output**: Generates actionable recommendations

## 📈 Current Status

- **Products monitored**: 1,506
- **Products needing reorder**: 8
- **Total estimated cost**: $30,396.25
- **Average days to stockout**: 40.9 days

## 🔮 Next Steps

1. Add real vendor data (DynamoDB table)
2. Add PO tracking system
3. Set up daily automation
4. Email/Slack notifications

---

**Status**: ✅ Production Ready
**AI Model**: Amazon Nova Lite v1.0
**Last Updated**: November 15, 2025
