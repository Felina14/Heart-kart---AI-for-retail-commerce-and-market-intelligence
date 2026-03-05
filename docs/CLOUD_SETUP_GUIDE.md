# HeartKart - Cloud Deployment Guide

A complete guide to understanding and managing the HeartKart cloud deployment on AWS.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [AWS Services Used](#aws-services-used)
4. [Environment Configuration](#environment-configuration)
5. [Agent Deployment (Bedrock AgentCore)](#agent-deployment-bedrock-agentcore)
6. [Backend Deployment (Lambda + API Gateway)](#backend-deployment-lambda--api-gateway)
7. [Vendor Caller Deployment (EC2)](#vendor-caller-deployment-ec2)
8. [Frontend Deployment (S3 + CloudFront)](#frontend-deployment-s3--cloudfront)
9. [All Deployed Agents](#all-deployed-agents)
10. [API Endpoints](#api-endpoints)
11. [DynamoDB Tables](#dynamodb-tables)
12. [Deployment Commands](#deployment-commands)
13. [ARN Update Workflow](#arn-update-workflow)
14. [Running the Cloud Backend Locally](#running-the-cloud-backend-locally)
15. [Project Structure](#project-structure)
16. [Troubleshooting](#troubleshooting)

---

## Overview

The cloud deployment runs the same HeartKart platform as the local setup, but with a fundamentally different architecture:

- **Local**: Backend imports agent code directly as Python modules
- **Cloud**: Backend calls **deployed agents** via AWS Bedrock AgentCore Runtime SDK

Each AI agent runs as an independent **Docker container** on Bedrock AgentCore. The Flask backend (`app_agentcore.py`) acts as a thin proxy — it receives frontend API requests and routes them to the appropriate deployed agent via `invoke_agent_runtime()`.

**Live URLs:**
- Frontend: `https://d18vvrckvpu5u9.cloudfront.net`
- Backend API: `https://h1p3mb0sh9.execute-api.us-east-1.amazonaws.com`

**AWS Account:** `583880312323` (profile: `heartkart-deploy`)

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                 Frontend (Next.js 14)                            │
│          S3 + CloudFront CDN                                     │
│          https://d18vvrckvpu5u9.cloudfront.net                   │
└───────────────────────┬──────────────────────────────────────────┘
                        │ REST API
                        ▼
┌──────────────────────────────────────────────────────────────────┐
│              API Gateway + Lambda                                │
│   https://h1p3mb0sh9.execute-api.us-east-1.amazonaws.com        │
│                                                                  │
│   lambda_handler.py → app_agentcore.py (Flask via serverless-wsgi)│
└──────┬──────────┬──────────────┬─────────────────────────────────┘
       │          │              │
       ▼          ▼              ▼
┌────────────┐ ┌──────────┐ ┌────────────────────────────────────┐
│  Bedrock   │ │ DynamoDB │ │  Vendor Caller (EC2)               │
│  AgentCore │ │          │ │  Caddy reverse proxy + aiohttp     │
│  Runtime   │ │          │ │  https://34-204-233-141.sslip.io   │
│            │ │          │ │                                    │
│  8 agents  │ │ 3 tables │ │  Twilio ↔ WebSocket ↔ Nova Sonic  │
│  (Docker)  │ │          │ │                                    │
└────────────┘ └──────────┘ └────────────────────────────────────┘
```

### How a request flows

1. User clicks a panel in the frontend dashboard
2. Frontend calls the API Gateway URL (e.g., `GET /api/replenishment/plan`)
3. API Gateway triggers the Lambda function
4. Lambda runs `app_agentcore.py` via `serverless-wsgi`
5. `app_agentcore.py` calls `invoke_agent_runtime()` with the agent's ARN
6. Bedrock AgentCore starts the agent's Docker container
7. The agent (Strands framework) processes the request using Bedrock Nova models + DynamoDB
8. Response flows back: Agent → AgentCore → Lambda → API Gateway → Frontend

### Key difference from local

```python
# LOCAL (app.py) — direct Python import
from replenishment_planner_agent import generate_replenishment_plan
result = generate_replenishment_plan()

# CLOUD (app_agentcore.py) — remote agent invocation
response = agentcore_client.invoke_agent_runtime(
    agentRuntimeArn="arn:aws:bedrock-agentcore:us-east-1:583880312323:runtime/heartkart_replenishment_planner-XOV1Fs7FQg",
    qualifier="DEFAULT",
    payload=json.dumps({"action": "generate_plan"}),
)
```

---

## AWS Services Used

| Service | Purpose | Details |
|---------|---------|---------|
| **Bedrock AgentCore Runtime** | Agent execution platform | 8 agents deployed as Docker containers |
| **Bedrock Models** | AI inference | Nova Lite (`amazon.nova-lite-v1:0`), Nova Pro (`amazon.nova-pro-v1:0`), Nova Sonic (`amazon.nova-sonic-v1:0`) |
| **Lambda** | Serverless compute | Runs the Flask backend (app_agentcore.py) |
| **API Gateway** | HTTP routing | REST API for frontend |
| **DynamoDB** | Data storage | Product catalog, sales history, call logs |
| **ECR** | Docker registry | Agent container images |
| **EC2** | Vendor Caller server | t3.small, Elastic IP, Caddy reverse proxy |
| **S3** | Static hosting | Frontend build output |
| **CloudFront** | CDN | Frontend distribution |
| **IAM** | Access control | `HeartKartAgentCoreRole` for agents |
| **CloudWatch** | Monitoring | Agent logs via OpenTelemetry |
| **CodeBuild** | CI/CD | Automated agent container builds |

---

## Environment Configuration

> **IMPORTANT**: The cloud backend does NOT use a `.env` file in production. Environment variables are set via Lambda console / CloudFormation. The `.env.example` is only for running `app_agentcore.py` locally for testing.

### Template File: `cloud/.env.example`

```bash
cd cloud
cp .env.example .env
# Only needed when running app_agentcore.py locally
```

### Variables Reference

#### AWS Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-east-1` | AWS region for all services |
| `AWS_PROFILE_AGENTCORE` | `heartkart-deploy` | AWS CLI profile with access to account 583880312323. Only used locally — Lambda uses IAM role |

#### Vendor Caller

| Variable | Default | Description |
|----------|---------|-------------|
| `VENDOR_CALLER_URL` | `https://34-204-233-141.sslip.io` | HTTPS URL of the EC2 Vendor Caller server |

#### Twilio (for vendor voice calls)

| Variable | Description | Where to get it |
|----------|-------------|-----------------|
| `TWILIO_ACCOUNT_SID` | Account SID (starts with `AC`) | [Twilio Console](https://console.twilio.com/) |
| `TWILIO_AUTH_TOKEN` | Auth token | [Twilio Console](https://console.twilio.com/) |
| `TWILIO_PHONE_NUMBER` | Twilio phone number (E.164 format) | Twilio → Phone Numbers |

#### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_DEBUG` | `0` | Set to `1` for debug mode (local only) |
| `API_URL` | `http://localhost:5000` | Internal API URL |

### Agent Container Environment

Each agent runs in a Docker container with these env vars set at build time:

| Variable | Value | Set In |
|----------|-------|--------|
| `AWS_REGION` | `us-east-1` | Dockerfile |
| `AWS_DEFAULT_REGION` | `us-east-1` | Dockerfile |
| `DOCKER_CONTAINER` | `1` | Dockerfile |
| `PRODUCTS_TABLE_NAME` | `valentines-products` | product_data_access.py default |

Agents inherit IAM permissions from the `HeartKartAgentCoreRole` — no AWS credentials are stored in containers.

---

## Agent Deployment (Bedrock AgentCore)

### Framework

All 8 primary agents use:
- **Strands framework** (`strands-agents`) — agent orchestration with `@tool` decorators
- **BedrockAgentCoreApp** — runtime wrapper that handles incoming requests
- **Bedrock Nova models** — AI inference (mostly Nova Lite, Email Drafter uses Nova Pro)

### How agents are built

Each agent is a Docker container:

```
cloud/agentcore_agents/<agent_name>/
├── agent.py                    # Agent logic (Strands @tool functions + BedrockAgentCoreApp)
├── product_data_access.py      # Local copy of shared DynamoDB access layer
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Container build (python3.13-bookworm-slim base)
├── .dockerignore               # Build exclusions
├── deploy_to_agentcore.py      # Per-agent deploy script
└── .bedrock_agentcore.yaml     # AgentCore config (ARN, ECR repo, settings)
```

### Dockerfile pattern (all agents)

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim
WORKDIR /app

ENV UV_SYSTEM_PYTHON=1 UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1 \
    DOCKER_CONTAINER=1 AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1

COPY requirements.txt requirements.txt
RUN uv pip install -r requirements.txt
RUN uv pip install aws-opentelemetry-distro>=0.10.1

RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore
EXPOSE 9000 8000 8080

COPY . .
CMD ["opentelemetry-instrument", "python", "-m", "agent"]
```

### Agent dependencies (requirements.txt)

```
strands-agents>=1.14.0
boto3>=1.34.0
botocore>=1.34.0
bedrock-agentcore-starter-toolkit>=0.1.0
```

### IAM Role

All agents share the `HeartKartAgentCoreRole` with:
- `AmazonBedrockFullAccess` — model inference
- `AmazonDynamoDBReadOnlyAccess` — read product/sales data
- `CloudWatchLogsFullAccess` — logging
- Custom inline policy — DynamoDB write to `valentines-products`, `heartkart-call-logs`

---

## Backend Deployment (Lambda + API Gateway)

### How it works

The cloud backend (`app_agentcore.py`) is a Flask app wrapped with `serverless-wsgi` for Lambda:

```python
# lambda_handler.py
import serverless_wsgi
from app_agentcore import app

def lambda_handler(event, context):
    return serverless_wsgi.handle_request(app, event, context)
```

API Gateway routes all `GET/POST /api/*` requests to this Lambda function.

### Lambda package structure

```
cloud/lambda-package/
├── app_agentcore.py              # Flask backend (agent proxy)
├── lambda_handler.py             # Lambda entry point (in cloud/ root, copied here)
├── product_data_access.py        # DynamoDB access layer
├── currency_utils.py             # USD ↔ INR conversion
├── nova_conversation_handler.py  # Nova Sonic conversation utilities
├── serverless_wsgi.py            # API Gateway ↔ Flask bridge
├── agents/replenishment_planner/
│   └── pdf_generator_v2.py       # PO PDF generation
└── (vendored libraries)
```

### Lambda dependencies (`requirements_lambda.txt`)

```
flask>=3.0.0
flask-cors>=4.0.0
boto3>=1.28.0
opensearch-py>=2.3.0
requests-aws4auth>=1.2.0
twilio>=8.0.0
python-dotenv>=1.0.0
serverless-wsgi>=3.0.0
reportlab>=4.0.0
```

### PDF Generation Lambda (separate)

A dedicated Lambda for PO PDF generation:

```
cloud/pdf-lambda-package/
├── pdf_lambda_handler.py                           # Entry point
└── agents/replenishment_planner/pdf_generator_v2.py # PDF logic
```

Input: `{"po": {...}}` → Output: `{"status": "success", "pdf_base64": "...", "po_number": "..."}`

---

## Vendor Caller Deployment (EC2)

The Vendor Caller is **not** an AgentCore agent — it runs on a dedicated EC2 instance because it requires persistent WebSocket connections for real-time audio streaming.

### Architecture

```
Internet (Twilio wss://) → Caddy (:443, auto-SSL) → aiohttp server (:8080) → Nova Sonic
```

### EC2 Setup

| Setting | Value |
|---------|-------|
| Instance type | `t3.small` |
| OS | Amazon Linux 2023 |
| Elastic IP | `34.204.233.141` |
| SSL | Caddy auto-SSL via `sslip.io` |
| URL | `https://34-204-233-141.sslip.io` |
| Ports | 80, 443 (Caddy), 8080 (app), 22 (SSH) |

### Server components

| File | Purpose |
|------|---------|
| `cloud_server.py` | Unified HTTP + WebSocket server (aiohttp) |
| `nova_sonic_voice_agent.py` | Nova Sonic bidirectional streaming agent |
| `nova_sonic_twilio_server.py` | Twilio audio ↔ Nova Sonic bridge |
| `make_conversational_call.py` | Call initiation via Twilio API |
| `check_call_status.py` | Call status polling |
| `Dockerfile.cloud` | Docker image for EC2 deployment |

### Server endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Health check |
| `GET` | `/api/info` | Service info + WebSocket URL |
| `POST` | `/api/initiate-call` | Start a Twilio call |
| `GET` | `/api/call-metadata/{call_sid}` | Get call metadata |
| `GET` | `/api/call-status/{order_id}` | Get order chain status |
| `POST` | `/api/store-transcript` | Store transcript + trigger vendor fallback |
| `GET` | `/api/calls` | List all calls |
| `WS` | `/media-stream` | Twilio bidirectional audio WebSocket |

### Audio pipeline

```
Twilio (mulaw 8kHz) → WebSocket → mulaw_to_pcm (resample to 16kHz) → Nova Sonic
Nova Sonic (PCM 24kHz) → pcm_to_mulaw (resample to 8kHz) → WebSocket → Twilio
```

---

## Frontend Deployment (S3 + CloudFront)

The Next.js frontend is built as static files and deployed to:
- **S3 bucket** — stores the build output
- **CloudFront CDN** — serves globally at `https://d18vvrckvpu5u9.cloudfront.net`

The frontend makes API calls to the API Gateway URL configured in its environment.

---

## All Deployed Agents

| # | Agent | Model | Memory | Timeout | Agent ID |
|---|-------|-------|--------|---------|----------|
| 1 | Replenishment Planner | Nova Lite | 512 MB | 120s | `heartkart_replenishment_planner-XOV1Fs7FQg` |
| 2 | Stockout Sentinel | Nova Lite | 512 MB | 120s | `heartkart_stockout_sentinel-SVao77AZkN` |
| 3 | Inventory Copilot | Nova Lite | 512 MB | 120s | `heartkart_inventory_copilot-AqG2gM81So` |
| 4 | Exception Investigator | Nova Lite | 512 MB | 120s | `heartkart_exception_investigator-JnGYePH7Ih` |
| 5 | Markdown Coach | Nova Lite | 512 MB | 120s | `heartkart_markdown_coach-4VuN2TB1l4` |
| 6 | Market Intelligence | Nova Lite | 1024 MB | 180s | `heartkart_market_intelligence-UV6jX76pJK` |
| 7 | Pricing Intelligence | Nova Lite | 1024 MB | 180s | `heartkart_pricing_intelligence-BpoKvYFNfq` |
| 8 | Email Drafter | **Nova Pro** | 512 MB | 120s | `heartkart_email_drafter-l15N4AEAaF` |

All agents use:
- Platform: `linux/arm64` (cost-optimized)
- Network mode: `PUBLIC` (can reach AWS services directly)
- Observability: CloudWatch via OpenTelemetry
- ECR repo pattern: `heartkart-agents/<agent_key>`

### What each agent does

**Replenishment Planner** — Analyzes stock levels and sales velocity to generate purchase order recommendations with ROP/EOQ calculations. Groups items by vendor, assigns urgency levels (CRITICAL/HIGH/MEDIUM/LOW).

**Stockout Sentinel** — Predicts which products will run out of stock within 30 days using sales velocity. Suggests substitute products from the same category/color/price range.

**Inventory Copilot** — Accepts natural language queries ("Show me wreaths under $50") and translates them into DynamoDB filters. Returns structured product results.

**Exception Investigator** — Detects sales anomalies using Z-score statistical analysis (80% historical / 20% recent window split). Classifies anomalies as DEMAND_SURGE, DEMAND_DROP, or STAGNANT.

**Markdown Coach** — Identifies aged inventory and recommends clearance strategies — markdown percentages, phased timelines, and product bundling suggestions.

**Market Intelligence** — Analyzes competitor pricing, category trends, and regional demand patterns from sales data.

**Pricing Intelligence** — Optimizes product pricing with price range analysis, competitor comparison, and demand elasticity calculations. Enforces minimum margin and maximum discount guardrails.

**Email Drafter** — Generates professional vendor emails for purchase orders. Uses Nova Pro (more capable model) for better writing quality. Can incorporate call transcript context from `heartkart-call-logs`.

---

## API Endpoints

All endpoints are served by `app_agentcore.py`. In production, they are accessed via the API Gateway URL.

### Health & Inventory

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/inventory` | All products (direct DynamoDB, no agent) |

### Replenishment Planner

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/replenishment/plan` | Full reorder recommendations |
| `GET` | `/api/replenishment/urgent` | Critical items only |
| `GET` | `/api/replenishment/by-vendor` | Grouped by vendor |
| `POST` | `/api/replenishment/export-po` | Generate PO PDF |
| `POST` | `/api/generate-po-pdf` | Alternative PDF generation |

### Stockout Sentinel

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/stockout/report` | Full stockout risk report |
| `GET` | `/api/stockout/substitutes/<sku>` | Substitutes for a product |
| `GET` | `/api/stockout/critical` | Critical stockouts only |
| `GET` | `/api/stockout/by-category` | Grouped by category |
| `POST` | `/api/stockout/substitute-suggestions` | Bulk substitute lookup |

### Inventory Copilot

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/copilot/query` | Natural language query |
| `GET` | `/api/copilot/suggestions` | Example queries |

### Exception Investigator

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/exceptions/investigate` | Anomaly detection (params: `days`, `threshold`) |
| `GET` | `/api/exceptions/summary` | Summary statistics |
| `GET` | `/api/exceptions/by-type/<type>` | Filter by anomaly type |

### Markdown & Clearance Coach

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/markdown/report` | Full clearance report |
| `GET` | `/api/markdown/aged-inventory` | Aged items (param: `threshold`) |
| `GET` | `/api/markdown/timeline` | Clearance timeline |
| `GET` | `/api/markdown/bundles` | Bundle suggestions |
| `GET` | `/api/markdown/summary` | Summary statistics |
| `POST` | `/api/markdown/apply` | Apply markdown to products |

### Market Intelligence

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET/POST` | `/api/market-intelligence` | Market report, competitor index, regional trends, category signals |

### Pricing Intelligence

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET/POST` | `/api/pricing-intelligence` | Price optimization, price range, competitor comparison, demand impact |

### Email Drafter

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/draft-email` | Generate vendor email |

### Vendor Calling

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/call-vendor` | Initiate vendor call (proxied to EC2) |
| `POST` | `/api/call-vendor-v2` | Alternative call endpoint |
| `GET` | `/api/get-call-status/<call_sid>` | Poll call status |
| `GET` | `/api/get-call-metadata/<call_sid>` | Call metadata |
| `POST` | `/api/store-transcript` | Store call transcript |
| `GET` | `/api/get-transcript/<call_sid>` | Get transcript |
| `GET` | `/api/call-logs` | All call history |

### Order & Vendor Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/vendors/all` | List all vendors |
| `GET` | `/api/orders` | List confirmed orders |
| `POST` | `/api/orders/mark-sent` | Mark order as sent |

---

## DynamoDB Tables

| Table Name | Contents | SKU Format | Records | GSI |
|------------|----------|------------|---------|-----|
| `valentines-products` | Product catalog | `VC-XXXXXXXX` | 1,000 | `category-index`, `vendor-index` |
| `SalesHistory` | Daily sales records | `SKU-XXXX` | 5,100 | — |
| `heartkart-call-logs` | Vendor call transcripts & metadata | Call SIDs | varies | — |

All agents access these tables via `product_data_access.py` (each agent has its own copy in its Docker container).

---

## Deployment Commands

### Deploy all agents at once

```bash
cd cloud/agentcore_agents
python deploy_all.py
```

### Deploy a single agent

```bash
python deploy_all.py --agent replenishment_planner
```

### Deploy without rebuilding Docker image

```bash
python deploy_all.py --skip-build
```

### Check deployment status

```bash
python deploy_all.py --status
```

### List all agents

```bash
python deploy_all.py --list
```

### Delete an agent deployment

```bash
python deploy_all.py --delete replenishment_planner
```

### Update app_agentcore.py with latest ARNs

After any agent redeployment:

```bash
cd cloud
python update_arns.py
```

This reads ARNs from all `.bedrock_agentcore.yaml` files and patches the `AGENT_ARNS` dict in `app_agentcore.py`.

### Deploy Lambda backend

```bash
cd cloud/lambda-package
zip -r lambda.zip *
aws lambda update-function-code \
  --function-name heartkart-backend \
  --zip-file fileb://lambda.zip
```

### Deploy Vendor Caller to EC2

```bash
cd cloud/agentcore_agents/vendor_caller
python deploy_to_ec2.py
```

This creates/updates: IAM instance profile, security group, Elastic IP, and EC2 instance with Docker + Caddy.

---

## ARN Update Workflow

When you redeploy any agent, its ARN may change. You must sync these back to the backend:

```
1. Agent redeployed → .bedrock_agentcore.yaml updated automatically with new ARN
2. Run: python cloud/update_arns.py → patches AGENT_ARNS in app_agentcore.py
3. Rebuild and redeploy the Lambda package (or restart app_agentcore.py locally)
```

The `update_arns.py` script:
- Scans all `cloud/agentcore_agents/<agent>/.bedrock_agentcore.yaml` files
- Extracts the `agent_arn` from each
- Uses regex to update the corresponding entry in `app_agentcore.py`

---

## Running the Cloud Backend Locally

You can run `app_agentcore.py` on your machine for testing. It will call the real deployed agents on AWS.

### Prerequisites

- AWS CLI configured with the `heartkart-deploy` profile
- Python packages: `pip install flask flask-cors boto3 python-dotenv twilio requests fpdf2`

### Steps

```bash
cd cloud
cp .env.example .env
# Edit .env with your Twilio credentials (if testing vendor calls)

python app_agentcore.py
```

You should see:

```
Using AWS profile: heartkart-deploy  (account: 583880312323)

======================================================================
 HeartKart Inventory Management API (AgentCore Cloud Edition)
======================================================================

 AgentCore Agents (8):
   • replenishment_planner: heartkart_replenishment_planner-XOV1Fs7FQg
   • stockout_sentinel: heartkart_stockout_sentinel-SVao77AZkN
   ...

 Running on http://localhost:5000
======================================================================
```

Then point the frontend at `http://localhost:5000` to test against the deployed agents.

---

## Project Structure

```
cloud/
├── app_agentcore.py                              # Flask backend (agent proxy, 1400 lines)
├── lambda_handler.py                             # Lambda entry point (serverless-wsgi)
├── product_data_access.py                        # Shared DynamoDB access layer
├── currency_utils.py                             # USD ↔ INR conversion
├── update_arns.py                                # ARN sync: YAML → app_agentcore.py
├── requirements_lambda.txt                       # Lambda Python dependencies
├── .env                                          # Environment variables (DO NOT COMMIT)
├── .env.example                                  # Template — copy to .env
│
├── agentcore_agents/                             # 8 deployed agents + vendor_caller
│   ├── deploy_all.py                             # Multi-agent deployment orchestrator
│   ├── product_data_access.py                    # Shared copy for agent containers
│   │
│   ├── replenishment_planner/                    # Agent: Reorder planning
│   │   ├── agent.py                              #   Strands @tool + BedrockAgentCoreApp
│   │   ├── product_data_access.py                #   Local DynamoDB access copy
│   │   ├── requirements.txt                      #   strands-agents, boto3, etc.
│   │   ├── Dockerfile                            #   python3.13-bookworm-slim
│   │   ├── .dockerignore
│   │   ├── deploy_to_agentcore.py                #   Per-agent deploy script
│   │   └── .bedrock_agentcore.yaml               #   AgentCore config + ARN
│   │
│   ├── stockout_sentinel/                        # Agent: Stockout prediction
│   │   └── (same file pattern as above)
│   │
│   ├── inventory_copilot/                        # Agent: NL query engine
│   │   └── (same file pattern)
│   │
│   ├── exception_investigator/                   # Agent: Anomaly detection
│   │   └── (same file pattern)
│   │
│   ├── markdown_coach/                           # Agent: Clearance optimization
│   │   └── (same file pattern)
│   │
│   ├── market_intelligence/                      # Agent: Market analytics
│   │   └── (same file pattern)
│   │
│   ├── pricing_intelligence/                     # Agent: Price optimization
│   │   └── (same file pattern)
│   │
│   ├── email_drafter/                            # Agent: Vendor email generation
│   │   └── (same file pattern)
│   │
│   └── vendor_caller/                            # Vendor Caller (EC2, not AgentCore)
│       ├── agent.py                              #   Call orchestration + fallback
│       ├── nova_sonic_voice_agent.py             #   Nova Sonic streaming agent
│       ├── nova_sonic_twilio_server.py           #   Twilio ↔ Nova Sonic bridge
│       ├── cloud_server.py                       #   Production aiohttp server
│       ├── make_conversational_call.py           #   Call initiation
│       ├── check_call_status.py                  #   Status polling
│       ├── start_server.sh                       #   Server startup script
│       ├── deploy_to_ec2.py                      #   EC2 deployment automation
│       ├── deploy_to_apprunner.py                #   App Runner deployment (alt)
│       ├── Dockerfile.cloud                      #   Docker image for cloud
│       ├── requirements.txt                      #   Agent dependencies
│       ├── requirements_cloud.txt                #   Cloud server dependencies
│       └── product_data_access.py                #   Local DynamoDB access copy
│
├── lambda-package/                               # Lambda deployment ZIP contents
│   ├── app_agentcore.py                          #   (copy of main backend)
│   ├── lambda_handler.py
│   ├── product_data_access.py
│   ├── currency_utils.py
│   ├── nova_conversation_handler.py
│   ├── serverless_wsgi.py
│   └── agents/replenishment_planner/
│       └── pdf_generator_v2.py
│
├── pdf-lambda-package/                           # Separate PDF generation Lambda
│   ├── pdf_lambda_handler.py
│   └── agents/replenishment_planner/
│       └── pdf_generator_v2.py
│
└── vendor_caller_lambda/                         # Legacy vendor caller (account 471112523638)
    ├── agentcore/                                #   Original AgentCore deployment
    │   ├── agent.py
    │   ├── deploy_to_agentcore.py
    │   └── ...
    └── lambda/                                   #   Lambda-based Twilio handler
        ├── twilio_handler.py
        └── requirements.txt
```

---

## Troubleshooting

### Agent returns empty or error response

- Check CloudWatch logs for the agent container (search for `heartkart_<agent_name>`)
- Verify the ARN in `app_agentcore.py` matches the deployed agent: `python update_arns.py`
- Ensure the agent's IAM role has DynamoDB access

### "Unknown agent" error from app_agentcore.py

- The `agent_key` passed to `invoke_agent()` doesn't match any key in `AGENT_ARNS`
- Check the `AGENT_ARNS` dict at the top of `app_agentcore.py`

### Lambda timeout (29s)

- API Gateway has a 29-second hard limit
- Some agent calls (market_intelligence, pricing_intelligence) may exceed this
- Solution: increase Lambda timeout and consider async invocation patterns

### Vendor call fails in production

1. Is the EC2 instance running? → Check `https://34-204-233-141.sslip.io/health`
2. Is Caddy serving SSL? → Ports 80/443 must be open in security group
3. Are Twilio credentials set in Lambda environment variables?
4. Is the receiving phone number Twilio-verified? (trial accounts only)

### ARNs out of sync after redeployment

```bash
cd cloud
python update_arns.py
# Then rebuild/redeploy the Lambda package
```

### AWS profile not found

If running locally and you see `profile 'heartkart-deploy' not found`:
```bash
aws configure --profile heartkart-deploy
# Enter: Access Key, Secret Key, Region (us-east-1), Output (json)
```

### Product names showing as generic

- DynamoDB `valentines-products` table should have real product names
- If names show as "Valentine Gift Item XXX", the DynamoDB table product names need to be updated
