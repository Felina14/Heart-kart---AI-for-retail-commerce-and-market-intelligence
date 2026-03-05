# HeartKart - Local Development Setup Guide

A complete guide to running the HeartKart Inventory Management System locally.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Environment Configuration](#environment-configuration)
5. [Starting the Backend](#starting-the-backend)
6. [Starting the Frontend](#starting-the-frontend)
7. [AI Agent Panels & API Endpoints](#ai-agent-panels--api-endpoints)
8. [Vendor Caller (Nova Sonic Voice Calls)](#vendor-caller-nova-sonic-voice-calls)
9. [DynamoDB Tables](#dynamodb-tables)
10. [Project Structure](#project-structure)
11. [Troubleshooting](#troubleshooting)

---

## Overview

HeartKart is a Valentine's Day retail inventory management platform powered by 9 AI agents built on AWS Bedrock Nova models. The system provides:

- **Automated replenishment planning** with purchase order generation
- **Stockout prediction** with substitute product recommendations
- **Natural language inventory queries** (no SQL needed)
- **Sales anomaly detection** using statistical analysis
- **Clearance optimization** with markdown strategies
- **Market and pricing intelligence** analytics
- **AI-powered vendor phone calls** using Amazon Nova Sonic
- **Automated email drafting** for vendor communication

The local setup runs the Flask backend and Next.js frontend on your machine, connecting to AWS DynamoDB and Bedrock services in the cloud.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│            Frontend (Next.js 14)                │
│         http://localhost:3001                    │
│  React 18 + TypeScript + Tailwind CSS           │
└───────────────────┬─────────────────────────────┘
                    │ REST API calls
                    ▼
┌─────────────────────────────────────────────────┐
│            Backend (Flask / Python)              │
│         http://localhost:5000                    │
│  local/app.py — all agent endpoints             │
└───────┬───────────┬──────────────┬──────────────┘
        │           │              │
        ▼           ▼              ▼
┌────────────┐ ┌──────────┐ ┌──────────────────┐
│ AWS Bedrock│ │ DynamoDB │ │  Twilio + ngrok  │
│ Nova Lite  │ │ Tables   │ │  (voice calls)   │
│ Nova Pro   │ │          │ │                  │
│ Nova Sonic │ │          │ │                  │
└────────────┘ └──────────┘ └──────────────────┘
```

**Key point**: The local backend (`local/app.py`) imports agent modules directly as Python packages — no AgentCore SDK, no Docker containers. All AI inference calls go to AWS Bedrock via `boto3`.

---

## Prerequisites

### Required Software

| Software        | Version  | Purpose                          |
|-----------------|----------|----------------------------------|
| Python          | 3.11+    | Backend and AI agents            |
| Node.js         | 20+      | Frontend (Next.js)               |
| npm             | 10+      | Frontend package manager         |
| AWS CLI         | v2       | AWS credentials and configuration|

### AWS Access

You need AWS credentials configured with access to:
- **Amazon Bedrock** (Nova Lite, Nova Pro, Nova Sonic models) in `us-east-1`
- **Amazon DynamoDB** (read/write to product and sales tables) in `us-east-1`

Configure via:
```bash
aws configure
# or set environment variables:
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-east-1
```

### Python Packages

Install from the `local/` directory:
```bash
cd local
pip install flask flask-cors boto3 python-dotenv reportlab twilio websockets
```

For vendor voice calls (Nova Sonic), also install:
```bash
pip install PyAudio audioop-lts smithy-aws-core aws-sdk-signers
```

### Node.js Packages

```bash
cd frontend/inventory-dashboard
npm install
```

---

## Environment Configuration

> **IMPORTANT**: The actual `.env` and `.env.local` files contain secrets (API keys, auth tokens) and must **never** be committed to version control. We provide `.env.example` template files instead. Copy them and fill in your values.

### Backend Environment

Template file: `local/.env.example`

```bash
cd local
cp .env.example .env
# Now edit .env and fill in your actual values
```

The `.env.example` file documents every variable. Here's what you need to configure:

#### Required Variables (all panels)

| Variable | Description | Where to get it |
|----------|-------------|-----------------|
| `USD_TO_INR` | Currency conversion rate (e.g. `89.62`) | Any forex site |

> AWS credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`) should be configured via `aws configure` or your shell profile — they are not stored in `.env`.

#### Required for Vendor Voice Calls Only

| Variable | Description | Where to get it |
|----------|-------------|-----------------|
| `TWILIO_ACCOUNT_SID` | Twilio account SID (starts with `AC`) | [Twilio Console](https://console.twilio.com/) → Dashboard |
| `TWILIO_AUTH_TOKEN` | Twilio auth token | [Twilio Console](https://console.twilio.com/) → Dashboard |
| `TWILIO_PHONE_NUMBER` | Your Twilio phone number (E.164 format, e.g. `+19401234567`) | [Twilio Console](https://console.twilio.com/) → Phone Numbers |
| `TEST_PHONE_NUMBER` | Phone number to receive test calls (E.164 format) | Your personal phone |
| `VERIFIED_PHONE_NUMBER` | Same as above — must be [Twilio-verified](https://console.twilio.com/) for trial accounts | Twilio → Verified Caller IDs |
| `NGROK_URL` | ngrok HTTPS URL (set after running `ngrok http 8080`) | ngrok terminal output |

#### Optional / Advanced Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-east-1` | AWS region for DynamoDB and Bedrock |
| `PRODUCTS_TABLE_NAME` | `valentines-products` | DynamoDB product catalog table |
| `FLASK_DEBUG` | `0` | Set to `1` for Flask auto-reload |
| `PRICING_CACHE_TTL_SECONDS` | `60` | Pricing agent cache duration |
| `PRICING_TIMEOUT_SECONDS` | `60` | Pricing agent request timeout |
| `REPLENISHMENT_SCAN_LIMIT` | `1500` | Max products to scan for reorder |
| `REPLENISHMENT_TAKE_LIMIT` | `100` | Max recommendations to return |
| `REPLENISHMENT_AI_TIMEOUT_SECONDS` | `15` | AI recommendation timeout |
| `NEXT_VENDOR_DELAY_SECONDS` | `5` | Delay between vendor fallback attempts |
| `CALL_RINGING_TIMEOUT` | `90` | Seconds to wait for call pickup |
| `API_URL` | `http://localhost:5000` | Internal API URL for vendor caller |

> **Note**: All panels except Vendor Caller work without any Twilio/ngrok configuration. You only need AWS credentials and `USD_TO_INR` to run the core dashboard.

### Frontend Environment

Template file: `frontend/inventory-dashboard/.env.example`

```bash
cd frontend/inventory-dashboard
cp .env.example .env.local
# Now edit .env.local and fill in your actual values
```

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_TEST_PHONE` | Phone number shown in the Vendor Call UI (E.164 format, e.g. `+919094840869`) |

> Variables prefixed with `NEXT_PUBLIC_` are exposed to the browser at build time. Do not put secrets in `.env.local`.

---

## Starting the Backend

```bash
cd local
python3 app.py
```

You should see:
```
======================================================================
 HeartKart Inventory Management API
======================================================================

 Replenishment Planner Endpoints:
  GET  /api/replenishment/plan
  GET  /api/replenishment/urgent
  GET  /api/replenishment/by-vendor
  POST /api/replenishment/export-po

 Stockout Sentinel Endpoints:
  GET  /api/stockout/report
  GET  /api/stockout/substitutes/<sku>
  ...

 Running on http://localhost:5000
======================================================================
```

Verify it's working:
```bash
curl http://localhost:5000/api/health
```

---

## Starting the Frontend

In a separate terminal:
```bash
cd frontend/inventory-dashboard
npm run dev
```

You should see:
```
  ▲ Next.js 14.x.x
  - Local:   http://localhost:3001
```

Open **http://localhost:3001** in your browser to see the dashboard.

---

## AI Agent Panels & API Endpoints

The dashboard has 9 AI-powered panels, each backed by a local Python agent:

### 1. Inventory Overview

| Detail       | Value                                          |
|-------------|------------------------------------------------|
| **Panel**   | Main inventory table + stats overview          |
| **Endpoint**| `GET /api/inventory`                           |
| **Agent**   | `local/product_data_access.py`                 |
| **Purpose** | Browse all 1000 products with search/filter    |

### 2. Replenishment Planner

| Detail       | Value                                                          |
|-------------|----------------------------------------------------------------|
| **Panel**   | Reorder recommendations with PO generation                     |
| **Endpoints**| `GET /api/replenishment/plan`, `POST /api/replenishment/export-po` |
| **Agent**   | `local/agents/replenishment_planner/replenishment_planner_agent.py` |
| **Purpose** | ROP/EOQ calculations, urgency classification, PDF PO export    |

### 3. Stockout Sentinel

| Detail       | Value                                              |
|-------------|---------------------------------------------------|
| **Panel**   | Stockout risk predictions + substitute suggestions |
| **Endpoints**| `GET /api/stockout/report`, `GET /api/stockout/substitutes/<sku>` |
| **Agent**   | `local/agents/stockout_sentinel/stockout_sentinel_agent.py` |
| **Purpose** | 30-day stockout predictions, risk scoring, substitutes |

### 4. Inventory Copilot

| Detail       | Value                                            |
|-------------|--------------------------------------------------|
| **Panel**   | Natural language query interface                 |
| **Endpoints**| `POST /api/copilot/query`, `GET /api/copilot/suggestions` |
| **Agent**   | `local/agents/inventory_copilot/inventory_copilot_agent.py` |
| **Purpose** | Ask questions like "Show me wreaths under $50"   |
| **Model**   | AWS Bedrock Nova Pro (most capable)              |

### 5. Exception Investigator

| Detail       | Value                                            |
|-------------|--------------------------------------------------|
| **Panel**   | Sales anomaly detection and investigation        |
| **Endpoints**| `GET /api/exceptions/investigate?days=30&threshold=2.0` |
| **Agent**   | `local/agents/exception_investigator/exception_investigator_agent.py` |
| **Purpose** | Detects DEMAND_SURGE, DEMAND_DROP, STAGNANT anomalies using Z-score analysis |

### 6. Markdown & Clearance Coach

| Detail       | Value                                            |
|-------------|--------------------------------------------------|
| **Panel**   | Aged inventory analysis with clearance strategies|
| **Endpoints**| `GET /api/markdown/report`, `GET /api/markdown/timeline` |
| **Agent**   | `local/agents/markdown_coach/markdown_coach_agent.py` |
| **Purpose** | Markdown % recommendations, phased clearance timelines, bundling |

### 7. Market Intelligence

| Detail       | Value                                            |
|-------------|--------------------------------------------------|
| **Panel**   | Market trends, competitor pricing, regional demand|
| **Endpoints**| `GET /api/market-intelligence/report`, `GET /api/market-intelligence/competitor-index` |
| **Agent**   | `local/agents/market_intelligence/market_intelligence_agent.py` |
| **Purpose** | Category trends, competitor price indexing, regional demand heatmap |

### 8. Pricing Intelligence

| Detail       | Value                                            |
|-------------|--------------------------------------------------|
| **Panel**   | Price optimization with competitor & demand analysis |
| **Endpoints**| `GET /api/pricing-intelligence/report`, `GET /api/pricing-intelligence/price-range/<sku>` |
| **Agent**   | `local/agents/pricing_intelligence/pricing_intelligence_agent.py` |
| **Purpose** | Price range analysis, competitor comparison, demand elasticity |

### 9. Vendor Caller + Email Drafter

| Detail       | Value                                            |
|-------------|--------------------------------------------------|
| **Panel**   | AI phone calls to vendors + email drafts         |
| **Endpoints**| `POST /api/call-vendor`, `POST /api/draft-email` |
| **Agent**   | `local/agents/vendor_caller/vendor_orchestrator_v2.py` + `local/agents/vendor_caller/nova_sonic_twilio_server.py` |
| **Purpose** | Real-time AI voice calls via Nova Sonic + Twilio, automated email generation |

---

## Vendor Caller (Nova Sonic Voice Calls)

The vendor caller is the most complex feature. It uses **Amazon Nova Sonic** for real-time bidirectional voice AI, bridged through **Twilio** phone calls and **ngrok** tunneling.

### How It Works

```
Your Phone ←→ Twilio ←→ ngrok tunnel ←→ WebSocket Server (port 8080) ←→ Nova Sonic AI
```

1. Flask backend initiates a Twilio call via `/api/call-vendor`
2. Twilio connects to a WebSocket URL (exposed via ngrok)
3. The WebSocket server bridges Twilio audio streams with Nova Sonic
4. Nova Sonic generates real-time conversational AI responses
5. The AI introduces itself, discusses the purchase order, and negotiates

### Running the Vendor Caller

You need **3 terminal windows** (in addition to the backend and frontend):

#### Terminal 1: ngrok tunnel

```bash
ngrok http 8080
```

Copy the generated HTTPS URL (e.g., `https://abc123.ngrok-free.dev`) and update `local/.env`:
```env
NGROK_URL=https://abc123.ngrok-free.dev
```

#### Terminal 2: WebSocket Server (Nova Sonic bridge)

```bash
cd local/agents/vendor_caller
python3 nova_sonic_twilio_server.py --websocket
```

This starts a WebSocket server on port 8080 that bridges Twilio audio with Nova Sonic.

#### Terminal 3: Backend (if not already running)

```bash
cd local
python3 app.py
```

The backend's `/api/call-vendor` endpoint uses `vendor_orchestrator_v2.py` to initiate Twilio calls and connect them to the WebSocket server.

### Testing a Vendor Call

From the frontend Replenishment Panel, click "Call Vendor" on any purchase order. Or test via API:

```bash
curl -X POST http://localhost:5000/api/call-vendor \
  -H "Content-Type: application/json" \
  -d '{
    "product_name": "Valentine Rose Bouquet",
    "category": "Flowers",
    "items": ["Valentine Rose Bouquet (100 units)"],
    "quantity": 100,
    "delivery_date": "February 10th",
    "total_amount": 2500.00
  }'
```

### Requirements for Voice Calls

- Twilio account with a verified phone number
- AWS credentials with Bedrock Nova Sonic access
- ngrok installed and running
- PyAudio and audioop-lts Python packages
- The phone number receiving the call must be Twilio-verified (for trial accounts)

---

## DynamoDB Tables

The local setup reads from these DynamoDB tables in `us-east-1`:

| Table Name            | Contents                    | SKU Format     | Records |
|-----------------------|-----------------------------|----------------|---------|
| `valentines-products` | Product catalog (1000 items)| `VC-XXXXXXXX`  | 1,000   |
| `SalesHistory`        | Daily sales records         | `SKU-XXXX`     | 5,100   |
| `heartkart-call-logs` | Vendor call transcripts     | Call SIDs       | varies  |

**Data access layer**: All agents use `local/product_data_access.py` which defaults to the `valentines-products` table. This module provides `get_all_products()`, `get_product_by_sku()`, `get_products_by_category()`, and related functions.

---

## Project Structure

```
HeartKart/
├── local/                                    # Local development
│   ├── app.py                                # Flask backend (port 5000)
│   ├── product_data_access.py                # Shared DynamoDB access layer
│   ├── currency_utils.py                     # USD ↔ INR conversion
│   ├── .env                                  # Environment variables (DO NOT COMMIT)
│   ├── .env.example                          # Template — copy to .env
│   └── agents/
│       ├── replenishment_planner/
│       │   ├── replenishment_planner_agent.py # ROP/EOQ calculations
│       │   └── pdf_generator_v2.py           # PO PDF generation
│       ├── stockout_sentinel/
│       │   └── stockout_sentinel_agent.py    # Risk prediction
│       ├── inventory_copilot/
│       │   └── inventory_copilot_agent.py    # NL query engine
│       ├── exception_investigator/
│       │   └── exception_investigator_agent.py # Z-score anomaly detection
│       ├── markdown_coach/
│       │   └── markdown_coach_agent.py       # Clearance optimization
│       ├── market_intelligence/
│       │   └── market_intelligence_agent.py  # Market analytics
│       ├── pricing_intelligence/
│       │   └── pricing_intelligence_agent.py # Price optimization
│       ├── email_drafter/
│       │   └── email_drafter_agent.py        # Vendor email generation
│       └── vendor_caller/
│           ├── vendor_orchestrator_v2.py     # Call orchestration logic
│           ├── nova_sonic_twilio_server.py   # WebSocket bridge server
│           ├── nova_sonic_voice_agent.py     # Nova Sonic AI agent
│           ├── make_conversational_call.py   # Twilio call initiator
│           └── vendor_database.py            # Vendor lookup
│
├── frontend/
│   └── inventory-dashboard/                  # Next.js 14 app
│       ├── app/                              # Next.js App Router pages
│       ├── components/
│       │   ├── InventoryTable.tsx             # Product table
│       │   ├── StatsOverview.tsx              # Summary cards
│       │   ├── DashboardHeader.tsx            # Navigation header
│       │   ├── ReplenishmentPanel.tsx         # Reorder planning
│       │   ├── StockoutPanel.tsx              # Stockout alerts
│       │   ├── CopilotPanel.tsx               # NL query chat
│       │   ├── ExceptionPanel.tsx             # Anomaly dashboard
│       │   ├── MarkdownPanel.tsx              # Clearance strategies
│       │   ├── MarketIntelligencePanel.tsx    # Market analytics
│       │   ├── PricingIntelligencePanel.tsx   # Price optimization
│       │   ├── CallVendorModal.tsx            # Voice call modal
│       │   └── NotificationsPanel.tsx         # Alert notifications
│       ├── .env.local                         # Frontend env vars (DO NOT COMMIT)
│       ├── .env.example                       # Template — copy to .env.local
│       └── package.json
│
├── cloud/                                    # AWS deployed version
│   ├── app_agentcore.py                      # Cloud Flask backend
│   └── agentcore_agents/                     # Deployed agents (Docker/ECR)
│
└── docs/                                     # Documentation
    ├── README.md
    ├── PRD.md
    ├── COST_ANALYSIS.md
    ├── WHICH_BACKEND_TO_USE.md
    └── LOCAL_SETUP_GUIDE.md                  # This file
```

---

## Troubleshooting

### Backend won't start

**Error**: `ModuleNotFoundError: No module named 'flask'`
```bash
pip install flask flask-cors boto3 python-dotenv reportlab
```

**Error**: `IndentationError` in any agent file
- Ensure all agent files use consistent 4-space indentation
- Run `python -c "import py_compile; py_compile.compile('agents/AGENT_DIR/AGENT_FILE.py')"` to check syntax

### Frontend won't start

**Error**: `Module not found` for a component
```bash
cd frontend/inventory-dashboard
npm install
```

### Panels show no data

- Verify AWS credentials: `aws sts get-caller-identity`
- Check DynamoDB access: `aws dynamodb describe-table --table-name valentines-products --region us-east-1`
- Ensure the backend is running on port 5000 and reachable
- Check the browser console (F12) for CORS or network errors

### Vendor call fails

1. Is ngrok running? → `ngrok http 8080`
2. Is the WebSocket server running? → `python3 nova_sonic_twilio_server.py --websocket`
3. Is NGROK_URL set in `local/.env`?
4. Is the receiving phone number Twilio-verified? (required for trial accounts)
5. Are Twilio credentials correct in `local/.env`?

### "0 anomalies" in Exception Investigator

- The `SalesHistory` table uses `SKU-XXXX` format while `valentines-products` uses `VC-XXXXXXXX`
- Anomaly detection works on SalesHistory data — products are enriched afterward
- If enrichment fails to find a matching product, placeholder data is used (this is expected behavior)

### Currency showing wrong values

- Check `USD_TO_INR` in `local/.env` — update to current exchange rate
- `local/currency_utils.py` handles all conversions

---

## Quick Start Summary

```bash
# Terminal 1: Backend
cd local
python3 app.py                    # → http://localhost:5000

# Terminal 2: Frontend
cd frontend/inventory-dashboard
npm run dev                        # → http://localhost:3001

# (Optional) Terminal 3: ngrok for voice calls
ngrok http 8080

# (Optional) Terminal 4: WebSocket server for voice calls
cd local/agents/vendor_caller
python3 nova_sonic_twilio_server.py --websocket
```

Open **http://localhost:3001** and all 9 panels should be functional.
