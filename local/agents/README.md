# 🤖 AI Agents

This folder contains all AI agents for the HeartKart inventory system.

## 📁 Structure

```
agents/
├── replenishment_planner/     # ✅ COMPLETE - Reorder recommendations
│   ├── replenishment_planner_agent.py
│   ├── replenishment_cli.py
│   ├── replenishment_api.py
│   └── README.md
│
├── ask_inventory_copilot/     # 🚧 Coming next
├── stockout_sentinel/         # 🚧 Coming next
├── daily_ops_summarizer/      # 🚧 Coming next
└── README.md                  # This file
```

## ✅ Completed Agents

### 1. Replenishment Planner
**Status**: Production Ready
**Location**: `agents/replenishment_planner/`
**Purpose**: AI-powered reorder recommendations

**Features**:
- Sales velocity calculation
- Stockout prediction
- ROP/EOQ calculations
- Amazon Nova AI analysis
- CLI, API, and frontend interfaces

**Quick Start**:
```bash
cd agents/replenishment_planner
python3 replenishment_planner_agent.py
```

**API**: `http://localhost:5001/api/replenishment/*`

**Frontend**: Dashboard → "🤖 Replenishment Planner" tab

---

## 🚧 Planned Agents

### 2. Ask-Inventory Copilot
**Status**: Not Started
**Purpose**: Natural language queries over inventory

**Features**:
- "Show me all red ornaments under $20 with low stock"
- "What's my total inventory value by category?"
- "Which products sold out in the last week?"

### 3. Stockout Sentinel
**Status**: Not Started
**Purpose**: Predict and prevent stockouts

**Features**:
- N-day stockout predictions
- Substitute product recommendations
- Auto-alerts for critical items

### 4. Daily Ops Summarizer
**Status**: Not Started
**Purpose**: Morning brief with key metrics

**Features**:
- Stockouts today
- Top reorders needed
- Late POs
- Cash tied up in inventory

### 5. Exception Investigator
**Status**: Not Started
**Purpose**: Flag inventory anomalies

**Features**:
- Sudden dips/spikes detection
- Count mismatches
- Negative margins
- Auto-create exception tickets

### 6. Lead-time & SLA Watchdog
**Status**: Not Started
**Purpose**: Vendor performance tracking

**Features**:
- On-time delivery rate
- Defect rate tracking
- Partial fill analysis
- Alternate vendor recommendations

### 7. Markdown & Clearance Coach
**Status**: Not Started
**Purpose**: Optimize clearance pricing

**Features**:
- Aged inventory identification
- Markdown ladder proposals
- Bundle-with-winners strategy

### 8. Bundle/Kit Optimizer
**Status**: Not Started
**Purpose**: Create profitable bundles

**Features**:
- Overstock + demand analysis
- Party bundle creation
- Attach rate optimization

### 9. Vendor Caller/Negotiator
**Status**: Not Started
**Purpose**: Automated vendor communication

**Features**:
- Place/expedite orders
- Confirm ETAs
- Capture quotes
- Twilio integration

### 10. Data Quality Fixer
**Status**: Not Started
**Purpose**: Maintain catalog quality

**Features**:
- Duplicate SKU detection
- Missing image detection
- Wrong category detection
- Auto-draft fixes

---

## 🎯 Build Order

### Phase 1: Foundation (Week 1)
1. ✅ Replenishment Planner
2. Ask-Inventory Copilot
3. Stockout Sentinel
4. Daily Ops Summarizer

### Phase 2: Enhancement (Week 2)
5. Exception Investigator
6. Lead-time & SLA Watchdog
7. Markdown & Clearance Coach

### Phase 3: Advanced (Week 3+)
8. Bundle/Kit Optimizer
9. Vendor Caller/Negotiator
10. Data Quality Fixer

---

## 🏗️ Agent Template

When creating a new agent, follow this structure:

```
agents/your_agent_name/
├── your_agent_name_agent.py    # Core logic
├── your_agent_name_cli.py      # CLI interface (optional)
├── your_agent_name_api.py      # API endpoints (optional)
├── test_your_agent_name.py     # Tests
├── README.md                   # Documentation
└── output/                     # Generated files
```

### Required Files

1. **`*_agent.py`** - Core agent logic
   - Main function that does the work
   - Uses Amazon Nova or other AI models
   - Connects to OpenSearch/DynamoDB

2. **`README.md`** - Documentation
   - What it does
   - How to use it
   - API endpoints (if any)
   - Configuration options

3. **`test_*.py`** - Test suite
   - Unit tests for core functions
   - Integration tests
   - Example usage

### Optional Files

4. **`*_cli.py`** - Interactive CLI
   - For operations team
   - Menu-driven interface

5. **`*_api.py`** - REST API
   - Flask endpoints
   - For dashboard integration

6. **Frontend Component** - React component
   - Location: `inventory-dashboard/components/`
   - Integrated into main dashboard

---

## 🔧 Common Utilities

### Data Access

```python
# OpenSearch
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
import boto3

credentials = boto3.Session().get_credentials()
awsauth = AWS4Auth(...)
opensearch_client = OpenSearch(...)

# DynamoDB
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('valentines-products')
```

### Amazon Nova

```python
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

response = bedrock.invoke_model(
    modelId='us.amazon.nova-lite-v1:0',
    body=json.dumps({
        'messages': [{'role': 'user', 'content': [{'text': prompt}]}],
        'inferenceConfig': {'temperature': 0.3, 'maxTokens': 2000}
    })
)
```

---

## 📊 Data Sources

All agents have access to:

- **OpenSearch**: 1,506 products with full inventory data
- **DynamoDB**: 9 tables (orders, carts, users, wishlists, etc.)
- **Order History**: Sales velocity calculations
- **Product Associations**: Recommendations data

See `../../DATA_INFRASTRUCTURE.md` for complete details.

---

## 🎓 Best Practices

1. **Error Handling**: Always handle API failures gracefully
2. **Fallbacks**: Provide default values when data is missing
3. **Testing**: Test with real data before deploying
4. **Documentation**: Keep README updated
5. **Logging**: Log important decisions and errors
6. **Performance**: Cache expensive calculations
7. **Security**: Never commit API keys or credentials

---

## 🚀 Deployment

### Local Development
```bash
cd agents/your_agent_name
python3 your_agent_name_agent.py
```

### API Server
```bash
python3 your_agent_name_api.py
# Runs on http://localhost:500X
```

### Production
- Deploy as Lambda function
- Schedule with EventBridge
- Integrate with dashboard

---

**Status**: 1/10 agents complete
**Next**: Ask-Inventory Copilot
**Last Updated**: November 15, 2025
