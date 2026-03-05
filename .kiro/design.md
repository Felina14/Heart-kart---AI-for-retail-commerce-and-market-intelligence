# Design Document

## Overview

The HeartKart AI Inventory Management System is a serverless, AI-first platform built on AWS that automates inventory operations for seasonal retail businesses. The system uses 9 specialized AI agents powered by AWS Bedrock to handle replenishment planning, stockout prediction, exception detection, natural language queries, clearance optimization, vendor communication, email drafting, market intelligence, and pricing optimization.

The architecture follows a three-tier model:
1. **Frontend Layer**: Next.js 14 dashboard with TypeScript
2. **Backend Layer**: Flask REST API — local dev (direct Python) or cloud (Lambda + API Gateway invoking AgentCore)
3. **Data Layer**: DynamoDB for product catalog, sales history, and call logs

The system is designed for Valentine's Day retail with 1,000+ SKUs, supporting real-time inventory updates, automated vendor calls using Amazon Nova Sonic, and intelligent pricing recommendations with guardrails.

## Architecture

### High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     Frontend Layer                            │
│  Next.js 14 Dashboard (React + TypeScript)                   │
│  Dev: http://localhost:3001                                  │
└────────────────────┬─────────────────────────────────────────┘
                     │ HTTPS REST API
                     ▼
┌──────────────────────────────────────────────────────────────┐
│                     Backend Layer                             │
│  Local:  Flask API (local/app.py) — direct Python agents     │
│  Cloud:  Flask API (cloud/app_agentcore.py) — AgentCore ARNs │
│          AWS Lambda + API Gateway                            │
└────────────────────┬─────────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  AWS Bedrock │ │  DynamoDB    │ │  DynamoDB    │
│ Nova Models  │ │  Products    │ │ SalesHistory │
│ AgentCore    │ │              │ │              │
└──────────────┘ └──────────────┘ └──────────────┘
        │
        ▼
┌──────────────────────────────────┐
│  Vendor Caller (EC2)             │
│  • Twilio (Voice Calls)         │
│  • Nova Sonic (Conversational)  │
│  • WebSocket Audio Bridge       │
└──────────────────────────────────┘
```

### Component Architecture

The system is organized into modular components with a dual local/cloud structure:

**Repository Structure**:
```
HeartKart/
├── local/              # Local development backend
│   ├── app.py          # Flask API — imports agents directly as Python modules
│   ├── agents/         # 9 agent implementations (plain Python + boto3)
│   ├── product_data_access.py  # DynamoDB access layer
│   └── currency_utils.py       # USD → INR conversion
├── cloud/              # Cloud deployment backend
│   ├── app_agentcore.py        # Flask API — invokes deployed AgentCore agents via ARNs
│   ├── agentcore_agents/       # 9 agent deployments (Strands + BedrockAgentCoreApp, Docker/ECR)
│   ├── lambda_handler.py       # Lambda entrypoint
│   ├── product_data_access.py  # DynamoDB access layer (copy for cloud)
│   └── update_arns.py          # Syncs ARNs from YAML → app_agentcore.py
├── frontend/           # Next.js dashboard
│   └── inventory-dashboard/
└── docs/               # Documentation
```

**AI Agent Components** (local/agents/ and cloud/agentcore_agents/):

All 8 analytical agents are deployed as AWS Bedrock AgentCore runtime agents using the Strands framework. The vendor caller runs on EC2 for real-time audio streaming.

Agent directories (same names in both local/ and cloud/):
- replenishment_planner/ — ROP/EOQ calculations and PO generation
- stockout_sentinel/ — Stockout prediction and substitute recommendations
- inventory_copilot/ — Natural language query processing
- exception_investigator/ — Anomaly detection using Z-score analysis
- markdown_coach/ — Clearance strategy optimization
- vendor_caller/ — Voice call orchestration with Nova Sonic (EC2)
- email_drafter/ — Professional email generation
- market_intelligence/ — Market analysis (competitor, regional, category)
- pricing_intelligence/ — Pricing optimization with guardrails

Each cloud agent follows the AgentCore deployment pattern:
- .bedrock_agentcore.yaml — Agent configuration and ARN
- agent.py — Core agent logic (Strands @tool decorators + BedrockAgentCoreApp)
- product_data_access.py — Local copy for Docker container
- deploy_to_agentcore.py — Deployment script
- requirements.txt — Python dependencies

**Backend Components**:

Local (local/):
- app.py — Main Flask application, imports agents directly as Python modules
- product_data_access.py — Unified DynamoDB access layer
- currency_utils.py — Currency conversion (USD to INR)

Cloud (cloud/):
- app_agentcore.py — Main Flask application, invokes deployed AgentCore agents via ARNs
- lambda_handler.py — AWS Lambda entrypoint (serverless-wsgi)
- product_data_access.py — Copy of DynamoDB access layer
- update_arns.py — Reads ARNs from .bedrock_agentcore.yaml files, patches app_agentcore.py

**Frontend Components** (frontend/inventory-dashboard/):
- app/layout.tsx — Root layout
- app/page.tsx — Main page
- components/ — React components for all AI agent panels
- lib/apiBaseUrl.ts — API URL configuration

**Deployment**:
- Backend (Cloud): AWS Lambda + API Gateway
- 8 AI Agents: AWS Bedrock AgentCore Runtime (Docker containers on ECR)
- Vendor Caller: EC2 instance with Elastic IP + Caddy reverse proxy
- Frontend: Next.js dev server (localhost:3001) or static export

## Components and Interfaces

### 1. Frontend Dashboard (Next.js 14 + TypeScript)

**Purpose**: Provide web-based interface for inventory managers to access all AI agents and view insights.

**Key Components**:
- InventoryTable: Real-time product display with search/filter
- AI Agent Panels: Collapsible panels for each of the 9 agents
- CallVendorModal: Vendor call dialog with real-time status
- StatsOverview: KPI summary cards
- NotificationsPanel: System alerts and pending actions

**Component Files**:
- components/ReplenishmentPanel.tsx
- components/StockoutPanel.tsx
- components/CopilotPanel.tsx
- components/ExceptionPanel.tsx
- components/MarkdownPanel.tsx
- components/MarketIntelligencePanel.tsx
- components/PricingIntelligencePanel.tsx
- components/CallVendorModal.tsx
- components/InventoryTable.tsx
- components/DashboardHeader.tsx
- components/StatsOverview.tsx
- components/NotificationsPanel.tsx

**Technology Stack**:
- Framework: Next.js 14 (React 18)
- Language: TypeScript
- Styling: Inline CSS (modern styling)
- State Management: React Hooks (useState, useEffect)
- API Client: Fetch API

**API Integration**:
- Base URL: Configured via lib/apiBaseUrl.ts (localhost:5000 for local dev)
- All requests use JSON format
- CORS enabled for cross-origin requests
- Error handling with user-friendly messages

### 2. Backend API (Flask)

**Purpose**: Provide REST API for all inventory operations and AI agent invocations.

**Local Backend** (local/app.py):
- Flask application with CORS support
- Imports agent modules directly as Python packages
- Runs on localhost:5000
- Direct DynamoDB access via product_data_access.py

**Cloud Backend** (cloud/app_agentcore.py):
- Flask application with CORS support
- Invokes deployed AgentCore agents via `invoke_agent_runtime` API using ARNs
- Deployed on AWS Lambda via serverless-wsgi
- No authentication for PoC/demo

**Key Modules**:

**product_data_access.py**:
- Unified interface for DynamoDB product table
- Functions: get_all_products(), get_product_by_sku(), get_products_by_category(), get_low_stock_products(), update_stock_quantity()
- Handles pagination and filtering
- Table name configurable via PRODUCTS_TABLE_NAME env var (default: `valentines-products`)

**currency_utils.py**:
- Currency conversion utilities
- Primary function: usd_to_inr() with configurable exchange rate
- Default rate: 89.6 INR per USD (configurable via USD_TO_INR env var)

### 3. AI Agent: Replenishment Planner

**Purpose**: Generate automated purchase order recommendations based on stock levels and sales velocity.

**Deployment**: AWS Bedrock AgentCore Runtime

**Implementation** (agents/replenishment_planner/agent.py):

**Core Algorithm**:
1. Query low-stock products from DynamoDB (stock below threshold)
2. For each product, calculate:
   - days_until_stockout = stock_quantity / sales_velocity
   - ROP = (velocity × lead_time_days) + (velocity × safety_stock_days)
   - EOQ = simplified calculation ensuring 30–60 days of stock
3. Classify urgency:
   - CRITICAL: days_until_stockout ≤ 3
   - HIGH: days_until_stockout ≤ 7
   - MEDIUM: days_until_stockout ≤ 14
   - LOW: days_until_stockout > 14
4. Group recommendations by vendor
5. Calculate estimated_cost = recommended_order_qty × price

**AI Model**: AWS Bedrock Nova Lite (`amazon.nova-lite-v1:0`)
- Used for: Analyzing patterns and providing contextual recommendations
- Temperature: 0.3 (deterministic)

**API Endpoints**:
- GET /api/replenishment/plan — Full replenishment plan
- GET /api/replenishment/urgent — Urgent items only
- GET /api/replenishment/by-vendor — Grouped by vendor
- POST /api/replenishment/export-po — Generate PO PDF

**Output Format**:
```json
{
  "recommendations": [
    {
      "sku": "string",
      "name": "string",
      "category": "string",
      "vendor": "string",
      "stock_quantity": "number",
      "reorder_point": "number",
      "recommended_order_qty": "number",
      "urgency": "CRITICAL|HIGH|MEDIUM|LOW",
      "days_until_stockout": "number",
      "estimated_cost": "number",
      "lead_time_days": "number"
    }
  ],
  "summary": {
    "total_items": "number",
    "critical_count": "number",
    "high_count": "number",
    "total_estimated_cost": "number"
  }
}
```

### 4. AI Agent: Stockout Sentinel

**Purpose**: Predict stockouts for the next 30 days and recommend substitute products.

**Deployment**: AWS Bedrock AgentCore Runtime

**Implementation** (agents/stockout_sentinel/agent.py):

**Core Algorithm**:
1. Query all products from DynamoDB
2. For each product, calculate:
   - days_until_stockout = stock_quantity / sales_velocity
   - risk_level based on days_until_stockout
3. For at-risk products, find substitutes:
   - Match by category
   - Match by color (if applicable)
   - Match by price_range (±20%)
4. Rank substitutes by similarity score

**Risk Classification**:
- CRITICAL: days_until_stockout ≤ 3
- HIGH: days_until_stockout ≤ 7
- MEDIUM: days_until_stockout ≤ 14
- LOW: days_until_stockout > 14

**AI Model**: AWS Bedrock Nova Lite (`amazon.nova-lite-v1:0`)
- Used for: Analyzing substitute suitability and providing recommendations
- Temperature: 0.4

**API Endpoints**:
- GET /api/stockout/report — Full stockout prediction report
- GET /api/stockout/substitutes/<sku> — Get substitutes for specific product
- GET /api/stockout/critical — Critical items only
- GET /api/stockout/by-category — Grouped by category
- POST /api/stockout/substitute-suggestions — AI-enhanced suggestions

### 5. AI Agent: Inventory Copilot

**Purpose**: Enable natural language queries over inventory data.

**Deployment**: AWS Bedrock AgentCore Runtime

**Implementation** (agents/inventory_copilot/agent.py):

**Core Algorithm**:
1. Receive natural language query from user
2. Use AWS Bedrock Nova Lite to:
   - Parse query intent (search, analytics, vendor-specific)
   - Extract filters (category, price range, stock level, vendor)
3. Execute query against DynamoDB via Strands @tool functions
4. Format results for display
5. Provide conversational response

**Query Types Supported**:
- Search queries: "Show me Valentine's gifts under ₹2000"
- Analytics queries: "What are my top 10 selling products?"
- Vendor queries: "Which items from Artisan Chocolate Co are low in stock?"
- Complex filters: "Show me all red decorations with less than 20 units"

**AI Model**: AWS Bedrock Nova Lite (`amazon.nova-lite-v1:0`)
- Used for: Natural language understanding and query generation
- Temperature: 0.4

**API Endpoints**:
- POST /api/copilot/query — Execute natural language query
- GET /api/copilot/suggestions — Get example queries

### 6. AI Agent: Exception Investigator

**Purpose**: Detect and investigate inventory anomalies using statistical analysis.

**Deployment**: AWS Bedrock AgentCore Runtime

**Implementation** (agents/exception_investigator/agent.py):

**Core Algorithm**:
1. Query sales history from `SalesHistory` DynamoDB table for configurable period (default 30 days)
2. For each SKU with ≥ 5 days of data:
   - Generate daily sales for entire date range (0 for missing days)
   - Split data: 80% historical / 20% recent
   - Calculate historical_avg, recent_avg, and std_dev
   - Calculate z_score = (recent_avg - historical_avg) / std_dev
3. Classify anomalies using multiplier threshold (default 1.5):
   - DEMAND_SURGE: recent_avg > historical_avg × threshold
     - Severity: HIGH if z_score > 3, else MEDIUM
   - STAGNANT: recent_avg = 0 (while historical_avg > 0)
     - Severity: MEDIUM
   - DEMAND_DROP: recent_avg < historical_avg / threshold
     - Severity: MEDIUM
4. Enrich anomalies with product data from Products table
5. Use AI to analyze root causes and provide recommendations

**AI Model**: AWS Bedrock Nova Lite (`amazon.nova-lite-v1:0`)
- Used for: Root cause analysis and actionable recommendations
- Temperature: 0.3

**API Endpoints**:
- GET /api/exceptions/investigate?days=30&threshold=1.5 — Full investigation
- GET /api/exceptions/summary — Summary without details
- GET /api/exceptions/by-type/<anomaly_type> — Filter by type

### 7. AI Agent: Markdown Coach

**Purpose**: Optimize clearance strategies for aged inventory.

**Deployment**: AWS Bedrock AgentCore Runtime

**Implementation** (agents/markdown_coach/agent.py):

**Core Algorithm**:
1. Query all products from DynamoDB
2. Calculate days_in_inventory for each product
3. Identify aged inventory (default threshold: 60 days)
4. For each aged item, use AI to recommend:
   - Optimal markdown percentage (10%, 20%, 30%, 40%)
   - Phased clearance timeline (Week 1, Week 2, Week 3)
   - Product bundling strategies
   - Revenue recovery projections
5. Prioritize by urgency and potential revenue impact

**AI Model**: AWS Bedrock Nova Lite (`amazon.nova-lite-v1:0`)
- Used for: Clearance strategy optimization and bundling suggestions
- Temperature: 0.7

**API Endpoints**:
- GET /api/markdown/report — Complete markdown report
- GET /api/markdown/aged-inventory — List aged items
- GET /api/markdown/timeline — Phased timeline
- GET /api/markdown/bundles — Bundle suggestions
- GET /api/markdown/summary — Summary statistics

### 8. AI Agent: Vendor Caller with Nova Sonic

**Purpose**: Automate vendor communication via AI-powered phone calls with real-time conversational AI.

**Deployment**: EC2 instance with Elastic IP (not AgentCore — requires persistent WebSocket connections for real-time audio streaming)

**Implementation** (agents/vendor_caller/):

**Architecture**:
```
User Action → Backend API → Twilio Call → EC2 WebSocket → Nova Sonic → Real-time Conversation
                                                                ↓
                                                        Transcript Storage (in-memory)
                                                                ↓
                                                        AI Decision Analysis
                                                                ↓
                                                        PO Generation (if YES)
```

**Core Components**:

**1. Cloud Server** (cloud_server.py):
- aiohttp WebSocket server with Caddy reverse proxy (HTTPS)
- Handles Twilio media stream connections
- Routes audio between Twilio and Nova Sonic voice agent

**2. Nova Sonic Voice Agent** (nova_sonic_voice_agent.py):
- Establishes bidirectional streaming with Amazon Nova Sonic (`amazon.nova-sonic-v1:0`)
- Handles audio encoding/decoding (Twilio μ-law 8kHz ↔ Nova Sonic PCM 16kHz)
- Maintains conversation context
- Stores complete transcript

**3. Nova Sonic Twilio Server** (nova_sonic_twilio_server.py):
- WebSocket bridge between Twilio Media Streams and Nova Sonic
- Manages call lifecycle and transcript capture

**Call Flow**:
1. User clicks "Call Vendor" in dashboard
2. Backend generates call script using Nova Lite
3. Twilio initiates call to vendor phone number
4. TwiML connects call to WebSocket server on EC2
5. EC2 WebSocket server establishes Nova Sonic session
6. Nova Sonic conducts real-time conversation
7. Audio streams bidirectionally (vendor ↔ Nova Sonic)
8. Conversation transcript stored in-memory (Python dict)
9. On call end, transcript analyzed for YES/NO decision
10. If YES: Generate PO, draft email, create notification
11. If NO: Try next vendor in priority order (multi-vendor fallback)

**AI Models**:
- AWS Bedrock Nova Lite: Call script generation and transcript analysis
- Amazon Nova Sonic (`amazon.nova-sonic-v1:0`): Real-time conversational AI

**EC2 Deployment**:
- Elastic IP: Configured via VENDOR_CALLER_URL env var
- HTTPS via Caddy reverse proxy with sslip.io domain
- aiohttp for async WebSocket handling

**API Endpoints**:
- POST /api/call-vendor — Initiate Nova Sonic call
- POST /api/call-vendor-v2 — Orchestrator V2 with multi-vendor fallback
- GET /api/call-logs — Get all call logs with transcripts
- GET /api/get-transcript/<call_sid> — Get specific transcript
- GET /api/get-call-status/<call_sid> — Get call status
- GET /api/get-call-metadata/<call_sid> — Get call metadata
- POST /api/store-transcript — Store transcript from WebSocket

**Call Types**:
- place_order: Place purchase order with order details
- follow_up_late: Follow up on late delivery
- check_availability: Check stock availability

### 9. AI Agent: Email Drafter

**Purpose**: Generate professional vendor emails with PO details and call summaries.

**Deployment**: AWS Bedrock AgentCore Runtime

**Implementation** (agents/email_drafter/agent.py):

**Core Algorithm**:
1. Receive email request with:
   - vendor_name, contact_person
   - po_number, items, total_amount, delivery_date
   - call_transcript (optional), call_summary (optional)
2. Use AWS Bedrock Nova Pro to generate professional email
3. Include PO details in structured format
4. Summarize call transcript if available
5. Maintain context-aware tone based on vendor relationship
6. Convert monetary amounts from USD to INR for display

**AI Model**: AWS Bedrock Nova Pro (`amazon.nova-pro-v1:0`)
- Used for: Professional email generation with context awareness (requires higher reasoning capability)
- Temperature: 0.7

**API Endpoints**:
- POST /api/draft-email — Draft vendor email

**Email Template Structure**:
- Subject: Purchase Order [PO_NUMBER] - [VENDOR_NAME]
- Greeting: Professional salutation
- Body: Order details, call summary, delivery expectations
- Closing: Professional sign-off with HeartKart contact information

### 10. AI Agent: Market Intelligence

**Purpose**: Provide market insights including competitor pricing, regional demand trends, and category signals.

**Deployment**: AWS Bedrock AgentCore Runtime

**Implementation** (agents/market_intelligence/agent.py):

**Core Functions**:

**1. Competitor Price Index Analysis**:
- Compares product prices against competitor prices
- Calculates price positioning (above/below/at market)
- Identifies pricing opportunities
- Provides competitive insights

**2. Regional Demand Trend Analysis**:
- Analyzes demand patterns by geographic region
- Identifies high-demand and low-demand regions
- Provides regional expansion opportunities
- Forecasts regional demand trends

**3. Category Trend Signals**:
- Analyzes market trends by product category
- Identifies growing and declining categories
- Provides category-specific insights
- Recommends inventory adjustments

**AI Model**: AWS Bedrock Nova Lite (`amazon.nova-lite-v1:0`) with Strands framework
- Used for: Market signal aggregation and AI-powered insights
- Temperature: 0.4

**API Endpoints**:
- GET /api/market-intelligence — Full market intelligence report
- GET /api/market-intelligence?report_type=competitor — Competitor analysis only
- GET /api/market-intelligence?report_type=regional — Regional trends only
- GET /api/market-intelligence?report_type=category — Category signals only

**Output Format**:
```json
{
  "success": true,
  "report_type": "full|competitor|regional|category",
  "timestamp": "2026-01-25T10:30:00Z",
  "data": {
    "competitor_analysis": {
      "price_index": "number",
      "positioning": "above|below|at_market",
      "opportunities": []
    },
    "regional_trends": {
      "high_demand_regions": [],
      "low_demand_regions": [],
      "growth_forecast": {}
    },
    "category_signals": {
      "growing_categories": [],
      "declining_categories": [],
      "recommendations": []
    }
  }
}
```

### 11. AI Agent: Pricing Intelligence

**Purpose**: Provide optimal pricing recommendations with guardrails and competitor comparisons.

**Deployment**: AWS Bedrock AgentCore Runtime

**Implementation** (agents/pricing_intelligence/agent.py):

**Core Functions**:

**1. Price Range Recommendations** (calculate_recommended_price_range):
- Calculates optimal price range for products
- Enforces guardrails:
  - min_margin_percent: Minimum profit margin (default 15%)
  - max_discount_percent: Maximum discount allowed (default 40%)
  - competitive_price_tolerance: ±5% vs competitor
  - premium_price_max_multiplier: Max price = cost × 1.5
  - clearance_price_min_multiplier: Min price = cost × 0.6
- Provides floor_price, ceiling_price, optimal_price
- Category-specific guardrails (see below)

**2. Competitor Price Comparison** (get_competitor_price_comparison):
- Compares product prices against competitors
- Calculates price_difference and price_position
- Identifies underpriced and overpriced products
- Provides competitive positioning insights

**3. Demand Impact Analysis** (calculate_demand_impact):
- Estimates demand change from price adjustments
- Calculates price elasticity (budget: -2.5, mid-range: -1.8, premium: -1.2)
- Projects revenue impact
- Provides expected_demand and expected_revenue

**4. Price Optimization Recommendations** (get_price_optimization_recommendations):
- Prioritizes products for price adjustments
- Ranks by revenue_impact
- Provides action recommendations (increase, decrease, maintain)
- Category-level optimization

**AI Model**: AWS Bedrock Nova Lite (`amazon.nova-lite-v1:0`) with Strands framework
- Used for: Pricing strategy insights and optimization recommendations
- Temperature: 0.4

**API Endpoints**:
- GET /api/pricing-intelligence — Full pricing intelligence report
- GET /api/pricing-intelligence?analysis_type=price_range — Price range only
- GET /api/pricing-intelligence?analysis_type=competitor_comparison — Competitor comparison
- GET /api/pricing-intelligence?analysis_type=demand_impact — Demand impact analysis
- GET /api/pricing-intelligence?analysis_type=optimization — Optimization recommendations

**Guardrail Configuration**:
```python
DEFAULT_GUARDRAILS = {
    'min_margin_percent': 15.0,           # Margin floor (15%)
    'max_discount_percent': 40.0,         # Maximum discount (40%)
    'competitive_price_tolerance': 5.0,   # ±5% vs competitor
    'premium_price_max_multiplier': 1.5,  # Max price: cost × 1.5
    'clearance_price_min_multiplier': 0.6, # Min price: cost × 0.6
}

# Category Overrides:
# Premium Categories (Premium Gifts, Luxury Items, Designer Collection):
#   min_margin_percent: 25.0, premium_price_max_multiplier: 2.0
# Budget Categories (Gifts Under ₹499, Budget Items):
#   min_margin_percent: 10.0, max_discount_percent: 50.0
```

**Output Format**:
```json
{
  "success": true,
  "analysis_type": "price_range|competitor_comparison|demand_impact|optimization",
  "timestamp": "2026-01-25T10:30:00Z",
  "data": {
    "price_range": {
      "floor_price": "number",
      "ceiling_price": "number",
      "optimal_price": "number",
      "current_price": "number",
      "guardrails": {
        "min_margin_percent": 15.0,
        "max_discount_percent": 40.0
      }
    },
    "competitor_comparison": {
      "our_price": "number",
      "competitor_avg_price": "number",
      "price_difference": "number",
      "price_position": "above|below|at_market"
    },
    "demand_impact": {
      "current_demand": "number",
      "expected_demand": "number",
      "demand_change_pct": "number",
      "current_revenue": "number",
      "expected_revenue": "number",
      "revenue_impact": "number"
    },
    "optimization": {
      "recommendations": [
        {
          "sku": "string",
          "current_price": "number",
          "recommended_price": "number",
          "action": "increase|decrease|maintain",
          "revenue_impact": "number",
          "priority": "high|medium|low"
        }
      ]
    }
  }
}
```

## Data Models

### DynamoDB Table: valentines-products (cloud) / Products (local)

**Table Name**: `valentines-products` (deployed account) / `Products` (local dev)
**Environment Variable**: `PRODUCTS_TABLE_NAME` (default: `valentines-products`)
**Primary Key**: sku (String)

**Schema**:
```json
{
  "sku": "string (PK)",
  "name": "string",
  "category": "string",
  "vendor_name": "string",
  "vendor_phone": "string",
  "vendor_email": "string",
  "price": "number (float, USD)",
  "stock_quantity": "number (integer)",
  "reorder_point": "number (integer)",
  "sales_velocity": "number (float, units/day)",
  "lead_time_days": "number (integer)",
  "last_restock_date": "string (ISO 8601)",
  "created_at": "string (ISO 8601)",
  "currency": "string (default: INR)",
  "delivery_options": ["array of strings"],
  "personalizable": "boolean",
  "color": "string (optional)",
  "description": "string (optional)",
  "rating": "number (optional)"
}
```

**Access Patterns**:
1. Get all products: Scan with pagination
2. Get product by SKU: GetItem
3. Get products by category: Scan with FilterExpression
4. Get low stock products: Scan with stock_quantity < threshold
5. Update stock quantity: UpdateItem
6. Batch get products: BatchGetItem

### DynamoDB Table: SalesHistory

**Table Name**: `SalesHistory`
**Primary Key**: sku (String) + date (String sort key)

**Schema**:
```json
{
  "sku": "string (PK)",
  "date": "string (SK, YYYY-MM-DD)",
  "quantity": "number (integer)"
}
```

**Access Patterns**:
1. Get sales by SKU: Query on sku
2. Get sales by date range: Scan with FilterExpression on date >= cutoff
3. Get all recent sales: Scan with date filter

**Usage**: Used by Exception Investigator agent for anomaly detection (Z-score analysis).

### DynamoDB Table: heartkart-call-logs

**Table Name**: `heartkart-call-logs`
**Primary Key**: call_id (String)

**Schema**:
```json
{
  "call_id": "string (PK)",
  "vendor_name": "string",
  "phone_number": "string",
  "call_type": "string (place_order|follow_up_late|check_availability)",
  "script": "string",
  "context": "string (JSON)",
  "status": "string (pending|initiated|in_progress|completed|failed)",
  "twilio_call_sid": "string",
  "transcript": "string (optional)",
  "decision": "string (YES|NO|UNCLEAR|optional)",
  "duration": "number (seconds)",
  "created_at": "string (ISO 8601)",
  "updated_at": "string (ISO 8601)"
}
```

**Access Patterns**:
1. Get all call logs: Scan with pagination
2. Get call by call_id: GetItem
3. Update call status: UpdateItem
4. Store transcript: UpdateItem

### In-Memory Stores

**call_metadata_store** (Python dict in app.py / app_agentcore.py):
- Key: call_sid (Twilio)
- Value: {vendor_name, product_name, quantity, po_number, contact_person, total_amount}
- Purpose: Store metadata for active calls

**call_transcripts_store** (Python dict):
- Key: call_sid (Twilio)
- Value: {transcript, conversation_history, decision, analysis, stored_at}
- Purpose: Store transcripts from WebSocket server (in-memory, not DynamoDB)

**orders_store** (Python list):
- Items: {po_number, vendor_name, product_name, items, total_amount, delivery_date, status, created_at, call_sid}
- Purpose: Track confirmed orders from successful vendor calls
- Status: pending_email | email_sent

### File System Storage

**PO PDFs**:
- Directory: generated_pos/
- Naming: PO-YYYYMMDD-HHMMSS.pdf
- Format: PDF with order details, vendor info, items, totals
- Access: GET /api/po-pdfs/<po_number>.pdf

## AgentCore Deployment Configuration

Each cloud agent has a `.bedrock_agentcore.yaml` file generated by the AgentCore CLI. The actual format:

```yaml
default_agent: heartkart_replenishment_planner
agents:
  heartkart_replenishment_planner:
    name: heartkart_replenishment_planner
    language: python
    entrypoint: /path/to/agent.py
    deployment_type: container
    platform: linux/arm64
    aws:
      execution_role: arn:aws:iam::583880312323:role/AmazonBedrockAgentCoreSDKRuntime-...
      account: '583880312323'
      region: us-east-1
      ecr_repository: 583880312323.dkr.ecr.us-east-1.amazonaws.com/bedrock-agentcore-heartkart_replenishment_planner
      network_configuration:
        network_mode: PUBLIC
      observability:
        enabled: true
    bedrock_agentcore:
      agent_id: heartkart_replenishment_planner-XOV1Fs7FQg
      agent_arn: arn:aws:bedrock-agentcore:us-east-1:583880312323:runtime/heartkart_replenishment_planner-XOV1Fs7FQg
    codebuild:
      project_name: bedrock-agentcore-heartkart_replenishment_planner-builder
    memory:
      mode: NO_MEMORY
```

**Deployed Agent ARNs** (AWS account 583880312323):

| Agent | Agent ID |
|-------|----------|
| Replenishment Planner | heartkart_replenishment_planner-XOV1Fs7FQg |
| Stockout Sentinel | heartkart_stockout_sentinel-SVao77AZkN |
| Inventory Copilot | heartkart_inventory_copilot-AqG2gM81So |
| Exception Investigator | heartkart_exception_investigator-JnGYePH7Ih |
| Markdown Coach | heartkart_markdown_coach-4VuN2TB1l4 |
| Market Intelligence | heartkart_market_intelligence-UV6jX76pJK |
| Pricing Intelligence | heartkart_pricing_intelligence-BpoKvYFNfq |
| Email Drafter | heartkart_email_drafter-l15N4AEAaF |

**ARN Update Workflow**:
After redeploying any agent:
1. `.bedrock_agentcore.yaml` gets updated with new ARN
2. Run `python cloud/update_arns.py` to sync all ARNs → `cloud/app_agentcore.py`
3. Restart cloud backend

## Correctness Properties

A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.

### Property 1: API Response Consistency

*For any* API endpoint request, the response should be valid JSON with standard fields: success (boolean), data (object), and timestamp (ISO 8601 string). When success is false, an error field (string) must be present.

**Validates: Requirements 13.2**

### Property 2: Complete Product Information

*For any* product retrieved from the API, the response should contain all required fields: SKU, name, category, vendor_name, vendor_phone, vendor_email, price, stock_quantity, sales_velocity, currency, delivery_options, and personalizable flag.

**Validates: Requirements 1.2**

### Property 3: Real-Time Update Propagation

*For any* product update operation, immediately querying the same product should return the updated values.

**Validates: Requirements 1.3**

### Property 4: Search and Filter Correctness

*For any* search query with filters (SKU, name, category, or vendor), all returned products should match the specified filter criteria.

**Validates: Requirements 1.4**

### Property 5: Reorder Recommendation Generation

*For any* product where stock_quantity < reorder_point, the replenishment plan should include a recommendation for that product.

**Validates: Requirements 2.1**

### Property 6: EOQ Calculation Correctness

*For any* product in the replenishment plan, the recommended_order_qty should be calculated to cover 30–60 days of demand based on sales_velocity, respecting vendor MOQ (minimum order quantity).

**Validates: Requirements 2.2**

### Property 7: Urgency Classification Correctness

*For any* product recommendation, the urgency classification should match the days_until_stockout:
- CRITICAL if days_until_stockout ≤ 3
- HIGH if 3 < days_until_stockout ≤ 7
- MEDIUM if 7 < days_until_stockout ≤ 14
- LOW if days_until_stockout > 14

**Validates: Requirements 2.3**

### Property 8: Stockout Prediction Calculation

*For any* product with non-zero sales_velocity, days_until_stockout should equal stock_quantity / sales_velocity.

**Validates: Requirements 3.1, 3.2**

### Property 9: Substitute Category Matching

*For any* stockout prediction with substitute recommendations, all substitutes should have the same category as the original product.

**Validates: Requirements 3.4**

### Property 10: Anomaly Detection Algorithm

*For any* product with ≥ 5 days of sales data, the anomaly detection should:
- Split data 80% historical / 20% recent
- Calculate z_score = (recent_avg - historical_avg) / std_dev
- Flag DEMAND_SURGE when recent_avg > historical_avg × threshold (default 1.5)
- Flag DEMAND_DROP when recent_avg < historical_avg / threshold
- Flag STAGNANT when recent_avg = 0

**Validates: Requirements 5.1, 5.2, 5.3, 5.4**

### Property 11: Call Script Generation

*For any* vendor call request, the system should generate a non-empty call script containing vendor_name and order_details.

**Validates: Requirements 7.1**

### Property 12: Transcript Decision Detection

*For any* call transcript containing clear affirmative language ("yes", "confirmed", "approved"), the decision should be detected as YES; for clear negative language ("no", "declined", "cannot"), the decision should be detected as NO.

**Validates: Requirements 7.8**

### Property 13: Vendor Fallback Logic

*For any* vendor call that results in a NO decision, the system should attempt to call the next vendor in the priority list if available.

**Validates: Requirements 7.9**

### Property 14: PO Number Format

*For any* generated purchase order, the po_number should match the format "PO-YYYYMMDD-HHMMSS" where YYYY is year, MM is month, DD is day, HH is hour, MM is minute, SS is second.

**Validates: Requirements 9.1**

### Property 15: PDF Generation Completeness

*For any* generated PO PDF, the document should contain vendor information, items list, quantities, prices, and delivery date.

**Validates: Requirements 9.2**

### Property 16: Vendor Priority Ordering

*For any* multi-vendor call orchestration with a preferred_vendor_name specified, the first vendor called should be the preferred vendor.

**Validates: Requirements 10.2**

### Property 17: JSON Response Format

*For any* API endpoint, the response should be valid JSON and include the standard fields: success (boolean), data (object), and timestamp (ISO 8601 string). When success is false, an error field (string) must be present.

**Validates: Requirements 13.2**

### Property 18: Market Intelligence Insights

*For any* market intelligence request, the response should contain non-empty insights and recommendations.

**Validates: Requirements 21.10**

### Property 19: Pricing Guardrail Enforcement — Margin Floor

*For any* pricing recommendation, the recommended price should satisfy: price ≥ cost / (1 - min_margin_percent/100), where min_margin_percent defaults to 15%.

**Validates: Requirements 22.1, 22.2**

### Property 20: Pricing Guardrail Enforcement — Maximum Discount

*For any* pricing recommendation, the recommended price should satisfy: price ≥ original_price × (1 - max_discount_percent/100), where max_discount_percent defaults to 40%.

**Validates: Requirements 22.1, 22.3**

### Property 21: Revenue Impact Calculation

*For any* pricing recommendation, the revenue_impact should be calculated as: (recommended_price - current_price) × expected_demand.

**Validates: Requirements 22.15**

## Error Handling

### API Error Responses

All API endpoints follow a consistent error response format:

```json
{
  "success": false,
  "error": "Human-readable error message",
  "details": "Optional detailed error information",
  "timestamp": "ISO 8601 timestamp"
}
```

**HTTP Status Codes**:
- 200: Success
- 400: Bad Request (invalid input)
- 404: Not Found (resource doesn't exist)
- 500: Internal Server Error
- 503: Service Unavailable (external service down)

### Error Handling Strategies

**1. DynamoDB Errors**:
- Connection failures: Return 500 with clear error message
- Item not found: Return 404 with clear message
- Scan/query failures: Return empty results with error logged

**2. AWS Bedrock / AgentCore Errors**:
- Model invocation failures: Return 500 with error details
- AgentCore agent unreachable: Return 503 with service name
- Timeout: Flask handles via request timeout

**3. Twilio Errors**:
- Call initiation failures: Log error, return 503 with fallback to email suggestion
- Invalid phone numbers: Return 400 with validation error
- Missing credentials: Return clear error message indicating missing TWILIO_* env vars

**4. Nova Sonic Errors**:
- Streaming failures: End call gracefully, store partial transcript
- Audio encoding errors: Log error, attempt reconnection
- Session timeout: End call gracefully
- Connection drops: Attempt reconnection

**5. PDF Generation Errors**:
- ReportLab not available: Use Lambda PDF generator endpoint as fallback
- Invalid PO data: Validate required fields before generation
- File system errors: Check permissions, create directory if needed

**6. Natural Language Query Errors**:
- Ambiguous queries: AI provides suggestions for clarification
- No results: Return helpful message with query suggestions
- Invalid filters: Return validation errors with examples

### Logging

**Current Implementation**:
- Python `print()` statements for key operations
- Flask request logging for all API endpoints
- Error stack traces logged on failures
- Twilio call events logged with call_sid and status

**What is Logged**:
- All API requests: endpoint, method, status
- All AI agent invocations: model, response summary
- All Twilio calls: call_sid, status, vendor info
- All errors: stack trace, context

**What is NOT Logged**:
- Sensitive credentials (API keys, tokens)
- Full phone numbers (masked in logs)
- Full AI prompts (logged as summary only)

## AI Model Summary

| Agent | Model | Temperature | Rationale |
|-------|-------|-------------|-----------|
| Replenishment Planner | Nova Lite | 0.3 | Deterministic calculations |
| Stockout Sentinel | Nova Lite | 0.4 | Prediction with some variance |
| Inventory Copilot | Nova Lite | 0.4 | Natural language understanding |
| Exception Investigator | Nova Lite | 0.3 | Statistical analysis |
| Markdown Coach | Nova Lite | 0.7 | Creative clearance strategies |
| Market Intelligence | Nova Lite | 0.4 | Market analysis |
| Pricing Intelligence | Nova Lite | 0.4 | Pricing analysis |
| Email Drafter | **Nova Pro** | 0.7 | Professional writing quality |
| Vendor Caller | Nova Sonic | N/A | Real-time voice conversation |

All agents except Email Drafter use `amazon.nova-lite-v1:0` for cost efficiency. Email Drafter uses `amazon.nova-pro-v1:0` for higher quality professional writing. Vendor Caller uses `amazon.nova-sonic-v1:0` for bidirectional voice streaming.

## Testing Strategy

> **Note**: Testing infrastructure is planned for future implementation. The sections below describe the intended testing approach. No test files currently exist in the codebase.

### Planned Unit Testing

**Framework**: pytest (Python), Jest (TypeScript)

**Coverage Target**: >80% code coverage

**Test Categories**:

**1. Data Access Layer Tests**:
- Test DynamoDB CRUD operations
- Test query and scan operations
- Test error handling for connection failures
- Test pagination logic
- Mock DynamoDB responses

**2. Business Logic Tests**:
- Test EOQ/ROP calculation with various inputs
- Test urgency classification logic (≤3/≤7/≤14/>14)
- Test anomaly detection (80/20 split, multiplier threshold)
- Test pricing guardrail enforcement (15% margin floor, 40% max discount)
- Test substitute product matching
- Use deterministic test data

**3. API Endpoint Tests**:
- Test all endpoints with valid inputs
- Test error responses for invalid inputs
- Test CORS headers
- Mock external services (Bedrock, Twilio)

**4. AI Agent Tests**:
- Test prompt generation
- Test response parsing
- Test fallback logic
- Mock Bedrock responses
- Validate output format

### Planned Integration Testing

**Test Scenarios**:

**1. End-to-End Replenishment Flow**:
- Query inventory → Generate replenishment plan → Export PO PDF → Verify PDF

**2. End-to-End Vendor Call Flow**:
- Initiate vendor call → WebSocket connection → Store transcript → Analyze decision → Generate PO if YES → Draft email

**3. End-to-End Natural Language Query Flow**:
- Submit query → Process with Bedrock → Query DynamoDB → Return formatted results

**4. End-to-End Market/Pricing Intelligence Flow**:
- Request analysis → Aggregate data → Generate AI insights → Return formatted report
