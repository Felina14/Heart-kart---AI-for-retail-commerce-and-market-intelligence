# HeartKart - AI Inventory Management System

**An intelligent, AI-powered inventory management platform for Valentine's Day retail with automated vendor communication via real-time voice calls.**

[![Production Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen)](https://d18vvrckvpu5u9.cloudfront.net)
[![AWS Deployment](https://img.shields.io/badge/AWS-Deployed-orange)](https://h1p3mb0sh9.execute-api.us-east-1.amazonaws.com)
[![AI Agents](https://img.shields.io/badge/AI%20Agents-9%20Active-blue)](#ai-agents)
[![Voice Calls](https://img.shields.io/badge/Voice%20Calls-Nova%20Sonic-purple)](#vendor-caller-agent-nova-sonic)

## Live Demo

- **Frontend Dashboard**: https://d18vvrckvpu5u9.cloudfront.net
- **Backend API**: https://h1p3mb0sh9.execute-api.us-east-1.amazonaws.com

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [AI Agents](#ai-agents)
- [Vendor Caller Agent (Nova Sonic)](#vendor-caller-agent-nova-sonic)
- [Technology Stack](#technology-stack)
- [Repository Structure](#repository-structure)
- [Quick Start](#quick-start)
- [API Endpoints](#api-endpoints)
- [Deployment](#deployment)
- [Cost Analysis](#cost-analysis)

---

## Overview

HeartKart transforms Valentine's Day retail inventory management from a manual, reactive process into an intelligent, proactive system that:

- **Reduces manual inventory tasks by 80%** through 9 specialized AI agents
- **Prevents stockouts** through predictive analytics and substitute recommendations
- **Automates vendor communication** with AI-powered real-time voice calls
- **Enables natural language queries** over inventory data — no SQL required
- **Optimizes clearance strategies** for aged inventory with markdown recommendations
- **Provides market and pricing intelligence** for competitive advantage

### Target Users
- Inventory managers at seasonal retail businesses
- Operations teams managing 500-5000 SKUs
- Small-to-medium businesses with single distribution center operations

---

## Key Features

### AI-Powered Automation
- **9 Specialized AI Agents** using AWS Bedrock Nova models
- **Real-time Voice Calls** to vendors using Amazon Nova Sonic + Twilio
- **Natural Language Queries** — ask questions in plain English
- **Predictive Analytics** for stockout prevention and demand forecasting

### Intelligent Inventory Management
- **Automated Reorder Recommendations** with ROP/EOQ calculations
- **Stockout Prediction** with substitute product suggestions
- **Exception Detection** using Z-score statistical anomaly analysis
- **Clearance Optimization** with phased markdown strategies and product bundling
- **Market Intelligence** — competitor pricing, category trends, regional demand
- **Pricing Intelligence** — price optimization, demand elasticity, competitor comparison

### Revolutionary Vendor Communication
- **AI Voice Calls** using Amazon Nova Sonic for human-like conversations
- **Automated Purchase Orders** via phone calls and email drafts
- **Call Transcription** for documentation and vendor fallback logic
- **Vendor Fallback** — if vendor 1 declines, auto-calls vendor 2

---

## Architecture

HeartKart runs in two modes: **local** (for development) and **cloud** (production on AWS).

### Cloud Architecture (Production)

```
┌─────────────────────────────────────────────────────────────────────┐
│                Frontend (Next.js 14 + TypeScript)                   │
│                S3 + CloudFront CDN                                  │
│                https://d18vvrckvpu5u9.cloudfront.net                │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ REST API
                           v
┌─────────────────────────────────────────────────────────────────────┐
│                API Gateway + Lambda                                 │
│    app_agentcore.py (Flask via serverless-wsgi)                     │
│    https://h1p3mb0sh9.execute-api.us-east-1.amazonaws.com          │
└──────┬──────────────┬──────────────────┬────────────────────────────┘
       │              │                  │
       v              v                  v
┌────────────┐  ┌──────────┐  ┌────────────────────────────────────┐
│  Bedrock   │  │ DynamoDB │  │  Vendor Caller (EC2)               │
│  AgentCore │  │          │  │  Caddy + aiohttp + Nova Sonic      │
│  Runtime   │  │ 3 tables │  │  https://34-204-233-141.sslip.io   │
│  8 agents  │  │          │  │  Twilio <-> WebSocket <-> AI Voice │
│  (Docker)  │  │          │  │                                    │
└────────────┘  └──────────┘  └────────────────────────────────────┘
```

### Local Architecture (Development)

```
┌─────────────────────────────────────────────────┐
│            Frontend (Next.js 14)                │
│            http://localhost:3001                 │
└───────────────────┬─────────────────────────────┘
                    │ REST API
                    v
┌─────────────────────────────────────────────────┐
│            Backend (Flask)                       │
│            http://localhost:5000                 │
│            local/app.py                         │
│            (imports agents as Python modules)    │
└───────┬───────────┬──────────────┬──────────────┘
        │           │              │
        v           v              v
  AWS Bedrock    DynamoDB     Twilio + ngrok
  (Nova models)  (3 tables)   (voice calls)
```

**Key difference**: Local backend imports agents directly as Python packages. Cloud backend calls deployed agents via `invoke_agent_runtime()` SDK.

---

## AI Agents

HeartKart has 9 specialized AI agents, each powered by AWS Bedrock:

### 1. Replenishment Planner
Analyzes stock levels and sales velocity to generate purchase order recommendations with ROP/EOQ calculations. Groups items by vendor, assigns urgency levels (CRITICAL/HIGH/MEDIUM/LOW). Exports PO as PDF.

**Endpoints**: `GET /api/replenishment/plan` | `POST /api/replenishment/export-po`

### 2. Stockout Sentinel
Predicts which products will run out of stock within 30 days. Calculates days-until-stockout using sales velocity. Suggests substitute products from the same category, color, and price range.

**Endpoints**: `GET /api/stockout/report` | `GET /api/stockout/substitutes/<sku>`

### 3. Inventory Copilot
Natural language query engine — ask questions like "Show me wreaths under $50" or "Which items from vendor X are low in stock?" Translates natural language into structured DynamoDB queries.

**Endpoints**: `POST /api/copilot/query` | `GET /api/copilot/suggestions`

### 4. Exception Investigator
Detects sales anomalies using Z-score statistical analysis with an 80/20 historical-to-recent window split. Classifies anomalies as DEMAND_SURGE, DEMAND_DROP, or STAGNANT. Configurable detection threshold and analysis window.

**Endpoints**: `GET /api/exceptions/investigate?days=30&threshold=2.0`

### 5. Markdown & Clearance Coach
Identifies aged inventory and recommends optimal clearance strategies — markdown percentages, phased timelines with revenue projections, and product bundling suggestions.

**Endpoints**: `GET /api/markdown/report` | `GET /api/markdown/timeline` | `GET /api/markdown/bundles`

### 6. Market Intelligence
Analyzes competitor pricing, category trends, and regional demand patterns. Provides competitor price indexing and demand heatmaps by region.

**Endpoints**: `GET/POST /api/market-intelligence`

### 7. Pricing Intelligence
Optimizes product pricing with price range analysis, competitor comparison, and demand elasticity calculations. Enforces minimum margin and maximum discount guardrails per category.

**Endpoints**: `GET/POST /api/pricing-intelligence`

### 8. Email Drafter
Generates professional vendor emails for purchase orders. Uses Nova Pro (more capable model) for better writing quality. Can incorporate call transcript context.

**Endpoints**: `POST /api/draft-email`

### 9. Vendor Caller (Nova Sonic)
Automates vendor phone calls using Amazon Nova Sonic for real-time bidirectional voice AI. Includes automatic vendor fallback logic — if vendor 1 declines, auto-calls vendor 2.

**Endpoints**: `POST /api/call-vendor` | `GET /api/get-call-status/<call_sid>`

---

## Vendor Caller Agent (Nova Sonic)

The Vendor Caller is the most innovative feature — it uses **Amazon Nova Sonic** (`amazon.nova-sonic-v1:0`) for real-time conversational AI phone calls.

### How It Works

```
Vendor's Phone <-> Twilio PSTN <-> WebSocket Server <-> Nova Sonic AI
                   (mulaw 8kHz)    (audio bridge)       (PCM 16/24kHz)
```

1. Backend receives a "Call Vendor" request from the frontend
2. Twilio initiates an outbound call to the vendor's phone
3. Twilio connects the call audio to a WebSocket server via ngrok (local) or EC2 (cloud)
4. The WebSocket server bridges Twilio audio (mulaw 8kHz) with Nova Sonic (PCM 16/24kHz)
5. Nova Sonic generates real-time conversational AI responses
6. The AI introduces itself as "Alex from HeartKart", discusses the purchase order, and handles negotiation
7. After the call, the transcript is stored and analyzed
8. If the vendor declines, the system automatically calls the next vendor (fallback logic)

### AI Persona

The AI introduces itself as a friendly inventory manager:
> "Hi there, this is Alex from HeartKart. I'm reaching out to place a purchase order with [Vendor Name] today."

### Call Flow Features

- **Real-time bidirectional conversation** — no pre-recorded messages
- **Context-aware** — AI knows the PO details, items, quantities, delivery dates
- **Automatic vendor fallback** — if vendor says NO, system calls an alternative vendor
- **Transcript storage** — all conversations logged for audit
- **Professional tone** — maintains business relationships

### Cost Per Call
- Twilio Voice: ~$0.01/minute
- Nova Sonic: ~$0.02/minute
- **Total: ~$0.03/minute**

---

## Technology Stack

| Layer | Technology | Details |
|-------|-----------|---------|
| **Frontend** | Next.js 14, React 18, TypeScript, Tailwind CSS | Deployed on S3 + CloudFront |
| **Backend** | Flask (Python 3.11+) | Local: direct imports / Cloud: Lambda + API Gateway |
| **AI Framework** | AWS Bedrock AgentCore Runtime, Strands framework | Docker containers with `@tool` decorators |
| **AI Models** | Nova Lite (7 agents), Nova Pro (Email Drafter), Nova Sonic (Voice) | All on AWS Bedrock |
| **Data Storage** | Amazon DynamoDB | `valentines-products` (1000 SKUs), `SalesHistory` (5100 records), `heartkart-call-logs` |
| **Voice** | Amazon Nova Sonic + Twilio | Bidirectional streaming, mulaw/PCM conversion |
| **Compute (Cloud)** | Lambda (backend), EC2 (vendor caller), ECR (agent containers) | Serverless + container-based |
| **CDN** | CloudFront | Frontend distribution |
| **Monitoring** | CloudWatch + OpenTelemetry | Agent container logging |

---

## Repository Structure

```
HeartKart/
├── local/                          # Local development backend
│   ├── app.py                      #   Flask backend (direct agent imports)
│   ├── product_data_access.py      #   Shared DynamoDB access layer
│   ├── currency_utils.py           #   USD <-> INR conversion
│   ├── .env.example                #   Environment template
│   └── agents/                     #   9 agent implementations
│       ├── replenishment_planner/
│       ├── stockout_sentinel/
│       ├── inventory_copilot/
│       ├── exception_investigator/
│       ├── markdown_coach/
│       ├── market_intelligence/
│       ├── pricing_intelligence/
│       ├── email_drafter/
│       └── vendor_caller/
│
├── cloud/                          # Cloud deployment
│   ├── app_agentcore.py            #   Flask backend (calls AgentCore agents)
│   ├── lambda_handler.py           #   Lambda entry point
│   ├── update_arns.py              #   ARN sync utility
│   ├── .env.example                #   Environment template
│   ├── agentcore_agents/           #   9 agents (8 on AgentCore + 1 on EC2)
│   │   ├── deploy_all.py           #     Deployment orchestrator
│   │   └── <agent_name>/           #     Each: agent.py, Dockerfile, requirements.txt
│   ├── lambda-package/             #   Lambda deployment ZIP
│   └── pdf-lambda-package/         #   PDF generation Lambda
│
├── frontend/
│   └── inventory-dashboard/        # Next.js 14 app
│       ├── app/                    #   App Router pages
│       ├── components/             #   12 React components (9 panels + shared)
│       ├── .env.example            #   Environment template
│       └── package.json
│
├── data/                           # Product catalog data
│   └── valentines_retail_catalog_1000_items.json
│
└── docs/                           # Documentation
    ├── README.md                   #   This file
    ├── PRD.md                      #   Product Requirements Document
    ├── COST_ANALYSIS.md            #   Detailed cost breakdown
    ├── WHICH_BACKEND_TO_USE.md     #   Local vs cloud backend guide
    ├── LOCAL_SETUP_GUIDE.md        #   Complete local dev setup guide
    └── CLOUD_SETUP_GUIDE.md        #   Complete cloud deployment guide
```

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 20+
- AWS CLI v2 configured with Bedrock + DynamoDB access
- Twilio account (for voice calls only)

### Local Development

```bash
# 1. Backend
cd local
cp .env.example .env          # Edit with your values
pip install flask flask-cors boto3 python-dotenv reportlab twilio websockets
python3 app.py                # Runs on http://localhost:5000

# 2. Frontend (new terminal)
cd frontend/inventory-dashboard
cp .env.example .env.local    # Edit with your values
npm install
npm run dev                   # Runs on http://localhost:3001

# 3. Voice calls (optional, 2 more terminals)
ngrok http 8080               # Terminal 3: tunnel
cd local/agents/vendor_caller
python3 nova_sonic_twilio_server.py --websocket  # Terminal 4: WebSocket server
```

Open **http://localhost:3001** — all 9 panels should be functional.

For detailed setup instructions, see:
- **[Local Setup Guide](LOCAL_SETUP_GUIDE.md)** — complete local development guide
- **[Cloud Setup Guide](CLOUD_SETUP_GUIDE.md)** — complete cloud deployment guide

---

## API Endpoints

**Base URLs:**
- Production: `https://h1p3mb0sh9.execute-api.us-east-1.amazonaws.com`
- Local: `http://localhost:5000`

### Core Endpoints

| Agent | Method | Endpoint | Description |
|-------|--------|----------|-------------|
| Health | `GET` | `/api/health` | Health check |
| Inventory | `GET` | `/api/inventory` | All products |
| Replenishment | `GET` | `/api/replenishment/plan` | Reorder recommendations |
| Replenishment | `POST` | `/api/replenishment/export-po` | Export PO as PDF |
| Stockout | `GET` | `/api/stockout/report` | Stockout risk report |
| Stockout | `GET` | `/api/stockout/substitutes/<sku>` | Substitute products |
| Copilot | `POST` | `/api/copilot/query` | Natural language query |
| Copilot | `GET` | `/api/copilot/suggestions` | Example queries |
| Exceptions | `GET` | `/api/exceptions/investigate` | Anomaly detection |
| Markdown | `GET` | `/api/markdown/report` | Clearance report |
| Markdown | `GET` | `/api/markdown/timeline` | Clearance timeline |
| Market Intel | `GET/POST` | `/api/market-intelligence` | Market analytics |
| Pricing Intel | `GET/POST` | `/api/pricing-intelligence` | Price optimization |
| Email | `POST` | `/api/draft-email` | Draft vendor email |
| Vendor Call | `POST` | `/api/call-vendor` | Initiate AI call |
| Vendor Call | `GET` | `/api/get-call-status/<call_sid>` | Call status |
| Vendor Call | `GET` | `/api/call-logs` | Call history |

---

## Deployment

### Cloud Deployment

**Agent deployment** (Bedrock AgentCore):
```bash
cd cloud/agentcore_agents
python deploy_all.py                        # Deploy all 8 agents
python deploy_all.py --agent <name>         # Deploy a single agent
python deploy_all.py --status               # Check deployment status
```

**ARN sync** (after agent redeployment):
```bash
cd cloud
python update_arns.py                       # Sync ARNs -> app_agentcore.py
```

**Lambda backend**:
```bash
cd cloud/lambda-package
zip -r lambda.zip *
aws lambda update-function-code --function-name heartkart-backend --zip-file fileb://lambda.zip
```

**Vendor Caller EC2**:
```bash
cd cloud/agentcore_agents/vendor_caller
python deploy_to_ec2.py
```

For the complete cloud deployment guide, see **[Cloud Setup Guide](CLOUD_SETUP_GUIDE.md)**.

---



## Documentation

| Document | Description |
|----------|-------------|
| [README.md](README.md) | This file — project overview |
| [LOCAL_SETUP_GUIDE.md](LOCAL_SETUP_GUIDE.md) | Complete local development setup |
| [CLOUD_SETUP_GUIDE.md](CLOUD_SETUP_GUIDE.md) | Complete cloud deployment guide |
---

**HeartKart — AI-Powered Inventory Management for Valentine's Day Retail**

*Transform your inventory operations with 9 specialized AI agents. Save time, reduce costs, and never run out of stock again.*
