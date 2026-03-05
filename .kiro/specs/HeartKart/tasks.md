# Implementation Plan: HeartKart AI Inventory Management System

## Overview

This implementation plan documents the HeartKart AI Inventory Management System - an AI-powered platform for Valentine's Day retail with 9 specialized AI agents deployed on AWS Bedrock AgentCore. The system automates replenishment planning, stockout prediction, vendor communication via voice calls, email drafting, market intelligence, and pricing optimization.

**Architecture**: Next.js 14 frontend → Flask REST API → AWS Bedrock AgentCore (8 agents) + EC2 (vendor caller) → DynamoDB

**Status**: Production deployment complete with 1000+ SKUs

## Tasks

- [x] 1. Set up core infrastructure
  - [x] 1.1 Create DynamoDB tables
    - Create `valentines-products` table with SKU primary key
    - Add GSI for category-index and vendor-index
    - Create `SalesHistory` table with composite key (sku + date)
    - Create `heartkart-call-logs` table for vendor call tracking
    - _Requirements: 1, 14_
    - _Files: cloud/agentcore_agents/product_data_access.py_
  
  - [x] 1.2 Implement product data access layer
    - Implement get_all_products() with pagination
    - Implement get_product_by_sku(), get_products_by_category(), get_products_by_vendor()
    - Implement get_low_stock_products() with threshold filtering
    - Add Decimal to float conversion for JSON serialization
    - _Requirements: 1, 14_
    - _Files: cloud/agentcore_agents/product_data_access.py, local/product_data_access.py_
  
  - [x] 1.3 Set up Flask API backend (local development)
    - Create Flask app with CORS support
    - Implement health check endpoint
    - Import agents as Python modules
    - Add error handling and logging
    - _Requirements: 1, 13_
    - _Files: local/app.py, local/currency_utils.py_
  
  - [x] 1.4 Set up Flask API backend (cloud deployment)
    - Create Flask app with CORS support
    - Configure bedrock-agentcore client with boto3
    - Implement invoke_agent() helper for AgentCore runtime
    - Create proxy endpoints for all 8 AgentCore agents
    - Configure Lambda deployment with serverless-wsgi
    - _Requirements: 1, 13_
    - _Files: cloud/app_agentcore.py, cloud/lambda_handler.py_

- [x] 2. Implement Replenishment Planner Agent
  - [x] 2.1 Build core replenishment logic
    - Implement ROP calculation: (velocity × lead_time) + (velocity × safety_stock)
    - Implement simplified EOQ calculation ensuring 30-60 days stock
    - Calculate days_until_stockout = stock / velocity
    - Classify urgency: CRITICAL (≤3d), HIGH (≤7d), MEDIUM (≤14d), LOW (>14d)
    - _Requirements: 2_
    - _Model: AWS Bedrock Nova Lite (amazon.nova-lite-v1:0)_
  
  - [x] 2.2 Implement vendor grouping and cost estimation
    - Group recommendations by vendor
    - Calculate estimated_cost = recommended_qty × price
    - Respect vendor MOQ (minimum order quantity)
    - _Requirements: 2_
  
  - [x] 2.3 Deploy to AgentCore
    - Create agent.py with Strands @tool decorators
    - Configure .bedrock_agentcore.yaml
    - Build and push Docker container to ECR
    - Deploy to AgentCore runtime
    - _Requirements: 2_
    - _Files: cloud/agentcore_agents/replenishment_planner/agent.py_
    - _ARN: heartkart_replenishment_planner-XOV1Fs7FQg_
  
  - [x] 2.4 Create API endpoints
    - GET /api/replenishment/plan - Full replenishment plan
    - GET /api/replenishment/urgent - Urgent items only
    - GET /api/replenishment/by-vendor - Grouped by vendor
    - POST /api/replenishment/export-po - Generate PO PDF
    - _Requirements: 2, 9_

- [x] 3. Implement Stockout Sentinel Agent
  - [x] 3.1 Build stockout prediction logic
    - Calculate days_until_stockout for all products
    - Assign risk levels: CRITICAL, HIGH, MEDIUM, LOW
    - Generate 30-day stockout predictions
    - _Requirements: 3_
    - _Model: AWS Bedrock Nova Lite (amazon.nova-lite-v1:0)_
  
  - [x] 3.2 Implement substitute recommendation engine
    - Match substitutes by category
    - Match by color (if applicable)
    - Match by price range (±20%)
    - Rank substitutes by similarity score
    - _Requirements: 3_
  
  - [x] 3.3 Deploy to AgentCore
    - Create agent.py with Strands framework
    - Deploy to AgentCore runtime
    - _Requirements: 3_
    - _Files: cloud/agentcore_agents/stockout_sentinel/agent.py_
    - _ARN: heartkart_stockout_sentinel-SVao77AZkN_
  
  - [x] 3.4 Create API endpoints
    - GET /api/stockout/report - Full stockout prediction report
    - GET /api/stockout/substitutes/<sku> - Get substitutes for product
    - GET /api/stockout/critical - Critical items only
    - GET /api/stockout/by-category - Grouped by category
    - _Requirements: 3_

- [x] 4. Implement Inventory Copilot Agent
  - [x] 4.1 Build natural language query parser
    - Parse query intent with Nova Lite
    - Extract filters: category, price range, stock level, vendor
    - Support search, analytics, and vendor-specific queries
    - _Requirements: 4_
    - _Model: AWS Bedrock Nova Lite (amazon.nova-lite-v1:0)_
  
  - [x] 4.2 Implement query execution with Strands tools
    - Execute queries against DynamoDB via @tool functions
    - Format results for conversational display
    - Handle complex filters and multi-criteria queries
    - _Requirements: 4_
  
  - [x] 4.3 Deploy to AgentCore
    - Deploy with Strands framework
    - _Requirements: 4_
    - _Files: cloud/agentcore_agents/inventory_copilot/agent.py_
    - _ARN: heartkart_inventory_copilot-AqG2gM81So_
  
  - [x] 4.4 Create API endpoints
    - POST /api/copilot/query - Execute natural language query
    - GET /api/copilot/suggestions - Get example queries
    - _Requirements: 4_

- [x] 5. Implement Exception Investigator Agent
  - [x] 5.1 Build anomaly detection algorithm
    - Query sales history from DynamoDB (configurable period, default 30 days)
    - Split data: 80% historical / 20% recent
    - Calculate Z-score = (recent_avg - historical_avg) / std_dev
    - Require minimum 5 days of data per SKU
    - _Requirements: 5_
    - _Model: AWS Bedrock Nova Lite (amazon.nova-lite-v1:0)_
  
  - [x] 5.2 Classify anomaly types
    - DEMAND_SURGE: recent > historical × threshold (default 1.5)
    - DEMAND_DROP: recent < historical / threshold
    - STAGNANT: recent = 0 (while historical > 0)
    - Assign severity: HIGH (z_score > 3), MEDIUM otherwise
    - _Requirements: 5_
  
  - [x] 5.3 Implement AI-powered root cause analysis
    - Analyze patterns with Nova Lite
    - Provide actionable recommendations
    - _Requirements: 5_
  
  - [x] 5.4 Deploy to AgentCore
    - _Requirements: 5_
    - _Files: cloud/agentcore_agents/exception_investigator/agent.py_
    - _ARN: heartkart_exception_investigator-JnGYePH7Ih_
  
  - [x] 5.5 Create API endpoints
    - GET /api/exceptions/investigate?days=30&threshold=1.5
    - GET /api/exceptions/summary
    - GET /api/exceptions/by-type/<anomaly_type>
    - _Requirements: 5_

- [x] 6. Implement Markdown Coach Agent
  - [x] 6.1 Build clearance strategy optimizer
    - Identify aged inventory (default 60 days threshold)
    - Recommend optimal markdown percentages (10-40%)
    - Generate phased clearance timeline
    - Suggest product bundling strategies
    - Project revenue recovery
    - _Requirements: 6_
    - _Model: AWS Bedrock Nova Lite (amazon.nova-lite-v1:0)_
  
  - [x] 6.2 Deploy to AgentCore
    - _Requirements: 6_
    - _Files: cloud/agentcore_agents/markdown_coach/agent.py_
    - _ARN: heartkart_markdown_coach-4VuN2TB1l4_
  
  - [x] 6.3 Create API endpoints
    - GET /api/markdown/report
    - GET /api/markdown/aged-inventory
    - GET /api/markdown/timeline
    - GET /api/markdown/bundles
    - POST /api/markdown/apply - Update price in DynamoDB
    - _Requirements: 6_

- [x] 7. Implement Market Intelligence Agent
  - [x] 7.1 Build market analysis tools
    - Implement competitor price index analysis
    - Implement regional demand trend analysis
    - Implement category trend signals
    - Support filtered reports (competitor, regional, category)
    - _Requirements: 21_
    - _Model: AWS Bedrock Nova Lite (amazon.nova-lite-v1:0)_
  
  - [x] 7.2 Deploy to AgentCore
    - _Requirements: 21_
    - _Files: cloud/agentcore_agents/market_intelligence/agent.py_
    - _ARN: heartkart_market_intelligence-UV6jX76pJK_
  
  - [x] 7.3 Create API endpoint
    - GET /api/market-intelligence?report_type=full|competitor|regional|category
    - _Requirements: 21_

- [x] 8. Implement Pricing Intelligence Agent
  - [x] 8.1 Build pricing optimization engine
    - Calculate recommended price ranges with guardrails
    - Enforce min_margin_percent (default 15%)
    - Enforce max_discount_percent (default 40%)
    - Apply category-specific overrides (premium: 25% margin, budget: 10% margin)
    - _Requirements: 22_
    - _Model: AWS Bedrock Nova Lite (amazon.nova-lite-v1:0)_
  
  - [x] 8.2 Implement competitor comparison and demand impact
    - Compare prices against competitors
    - Calculate demand impact using price elasticity
    - Generate optimization recommendations by revenue impact
    - _Requirements: 22_
  
  - [x] 8.3 Deploy to AgentCore
    - _Requirements: 22_
    - _Files: cloud/agentcore_agents/pricing_intelligence/agent.py_
    - _ARN: heartkart_pricing_intelligence-BpoKvYFNfq_
  
  - [x] 8.4 Create API endpoint
    - GET /api/pricing-intelligence?analysis_type=price_range|competitor_comparison|demand_impact|optimization
    - _Requirements: 22_

- [x] 9. Implement Email Drafter Agent
  - [x] 9.1 Build professional email generator
    - Generate emails with Nova Pro for higher quality
    - Include PO details (items, amounts, delivery dates)
    - Summarize call transcripts when available
    - Maintain context-aware tone
    - Convert USD to INR for display
    - _Requirements: 8_
    - _Model: AWS Bedrock Nova Pro (amazon.nova-pro-v1:0)_
  
  - [x] 9.2 Deploy to AgentCore
    - _Requirements: 8_
    - _Files: cloud/agentcore_agents/email_drafter/agent.py_
    - _ARN: heartkart_email_drafter-l15N4AEAaF_
  
  - [x] 9.3 Create API endpoint
    - POST /api/draft-email
    - _Requirements: 8_

- [x] 10. Implement Vendor Caller with Nova Sonic (EC2)
  - [x] 10.1 Set up EC2 infrastructure
    - Launch EC2 instance with Elastic IP
    - Configure Caddy reverse proxy for HTTPS
    - Set up sslip.io domain (e.g., 34-204-233-141.sslip.io)
    - Install Python dependencies
    - _Requirements: 7, 11_
  
  - [x] 10.2 Build WebSocket server for Twilio Media Streams
    - Implement aiohttp WebSocket server (cloud_server.py)
    - Handle Twilio media stream connections
    - Route audio between Twilio and Nova Sonic
    - _Requirements: 7, 11_
    - _Files: cloud/agentcore_agents/vendor_caller/cloud_server.py_
  
  - [x] 10.3 Implement Nova Sonic voice agent
    - Establish bidirectional streaming with Nova Sonic
    - Handle audio encoding/decoding (μ-law 8kHz ↔ PCM 16kHz)
    - Maintain conversation context
    - Store complete transcript
    - _Requirements: 7, 11_
    - _Model: Amazon Nova Sonic (amazon.nova-sonic-v1:0)_
    - _Files: cloud/agentcore_agents/vendor_caller/nova_sonic_voice_agent.py_
  
  - [x] 10.4 Build Twilio-Nova Sonic bridge
    - Implement WebSocket bridge (nova_sonic_twilio_server.py)
    - Manage call lifecycle
    - Capture transcript during call
    - _Requirements: 7, 11_
    - _Files: cloud/agentcore_agents/vendor_caller/nova_sonic_twilio_server.py_
  
  - [x] 10.5 Implement multi-vendor fallback orchestration
    - Query vendors by category from DynamoDB
    - Try vendors in priority order
    - Analyze transcripts for YES/NO decisions with AI
    - Automatically call next vendor on rejection
    - Track all call attempts with decisions
    - _Requirements: 7, 10_
  
  - [x] 10.6 Create vendor caller API endpoints
    - POST /api/call-vendor - Initiate Nova Sonic call
    - POST /api/call-vendor-v2 - Orchestrator with multi-vendor fallback
    - GET /api/get-call-status/<call_sid>
    - GET /api/get-call-metadata/<call_sid>
    - POST /api/store-transcript
    - GET /api/get-transcript/<call_sid>
    - _Requirements: 7, 10, 11_

- [x] 11. Implement Purchase Order Management
  - [x] 11.1 Build PO PDF generator
    - Generate professional PDFs with ReportLab library
    - Include vendor info, items, quantities, prices (INR)
    - Add HeartKart branding and professional layout
    - Upload PDFs to S3 for persistent storage
    - _Requirements: 9_
    - _Files: cloud/app_agentcore.py (_generate_po_pdf function)_
  
  - [x] 11.2 Implement notification system
    - Create success notifications (YES decision)
    - Create rejection notifications (NO decision)
    - Include PO details, email body, PDF URL
    - Track rejected vendors in fallback scenarios
    - _Requirements: 9, 10_
  
  - [x] 11.3 Create PO API endpoints
    - POST /api/generate-po-pdf
    - GET /api/po-pdfs/<po_number>.pdf
    - _Requirements: 9_

- [x] 12. Build Next.js Frontend Dashboard
  - [x] 12.1 Set up Next.js 14 project
    - Initialize with TypeScript
    - Configure API base URL (localhost:5000)
    - Set up layout and routing
    - Implement CORS-compatible API client
    - _Requirements: 12_
    - _Files: frontend/inventory-dashboard/app/layout.tsx, app/page.tsx_
  
  - [x] 12.2 Build inventory table component
    - Fetch inventory from API
    - Display product details (SKU, name, category, vendor, stock, price)
    - Implement search and category filter
    - Add stock level indicators
    - _Requirements: 12_
    - _Files: frontend/inventory-dashboard/components/InventoryTable.tsx_
  
  - [x] 12.3 Build AI agent panels
    - ReplenishmentPanel: Display reorder recommendations
    - StockoutPanel: Display stockout predictions and substitutes
    - CopilotPanel: Natural language query interface
    - ExceptionPanel: Display anomaly reports
    - MarkdownPanel: Display clearance recommendations
    - MarketIntelligencePanel: Display market insights
    - PricingIntelligencePanel: Display pricing recommendations
    - _Requirements: 12_
    - _Files: frontend/inventory-dashboard/components/*Panel.tsx_
  
  - [x] 12.4 Build call vendor modal
    - Modal UI with vendor selection
    - Display call status (initiated, in-progress, completed)
    - Show real-time call progress
    - Display transcript when available
    - Handle fallback vendor notifications
    - _Requirements: 12_
    - _Files: frontend/inventory-dashboard/components/CallVendorModal.tsx_
  
  - [x] 12.5 Build notifications panel
    - Store notifications in localStorage
    - Display success and rejection notifications
    - Show pending email actions
    - Provide action buttons (send email, view PO)
    - _Requirements: 12_
    - _Files: frontend/inventory-dashboard/components/NotificationsPanel.tsx_
  
  - [x] 12.6 Build dashboard header and stats
    - Display KPI summary cards
    - Show total products, low stock, critical stockouts
    - Add refresh functionality
    - _Requirements: 12_
    - _Files: frontend/inventory-dashboard/components/DashboardHeader.tsx_

- [x] 13. Deploy to AWS
  - [x] 13.1 Deploy all AgentCore agents
    - Configure .bedrock_agentcore.yaml for each agent
    - Build Docker containers
    - Push to ECR
    - Deploy to AgentCore runtime
    - Extract ARNs and update app_agentcore.py
    - _Requirements: All_
    - _Files: cloud/agentcore_agents/*/deploy_to_agentcore.py, cloud/update_arns.py_
  
  - [x] 13.2 Deploy vendor caller to EC2
    - Configure Twilio credentials
    - Start aiohttp WebSocket server
    - Test Nova Sonic voice calls
    - _Requirements: 7, 11_
  
  - [x] 13.3 Deploy Flask API to Lambda
    - Configure serverless-wsgi
    - Package dependencies
    - Deploy with API Gateway
    - Configure IAM roles
    - _Requirements: 13_
    - _Files: cloud/lambda_handler.py_
  
  - [x] 13.4 Create batch deployment script
    - Create deploy_all.py for all agents
    - Automate ARN updates
    - _Requirements: All_
    - _Files: cloud/agentcore_agents/deploy_all.py_

- [x] 14. Seed product catalog and sales data
  - [x] 14.1 Populate product catalog
    - Create 1000+ Valentine's Day SKUs
    - Include categories: Chocolates, Grooming Kits, Personalized Gifts, Fashion
    - Add vendor information (name, phone, email, priority)
    - Set realistic stock levels and sales velocities
    - _Requirements: 1_
  
  - [x] 14.2 Generate sales history
    - Create 30-90 days of sales data per SKU
    - Include normal patterns and anomalies
    - Support Z-score analysis (≥5 days per SKU)
    - _Requirements: 5_

- [ ] 15. Implement testing infrastructure
  - [ ] 15.1 Write unit tests
    - Test product_data_access.py functions
    - Test currency conversion
    - Test ROP/EOQ calculations
    - Test anomaly detection algorithm
    - Test substitute matching logic
    - _Requirements: 20_
  
  - [ ] 15.2 Write integration tests
    - Test all Flask API endpoints
    - Test AgentCore agent invocations
    - Test vendor caller WebSocket connections
    - Test multi-vendor fallback flow
    - Test PO PDF generation
    - _Requirements: 20_
  
  - [ ] 15.3 Validate AI agent quality
    - Test natural language query accuracy
    - Validate replenishment recommendations
    - Validate stockout predictions
    - Test email quality and professionalism
    - Test Nova Sonic conversation quality
    - _Requirements: 20_
  
  - [ ] 15.4 Perform load testing
    - Test with 1000+ SKUs
    - Test concurrent API requests
    - Test DynamoDB query performance
    - Test Lambda cold start times
    - _Requirements: 16_

- [ ] 16. Future enhancements
  - [ ] 16.1 Add user authentication
    - Set up AWS Cognito user pool
    - Implement login/logout flow
    - Add JWT token validation
    - Implement role-based access control
    - _Requirements: 15_
  
  - [ ] 16.2 Integrate email sending
    - Configure AWS SES
    - Implement send email function
    - Attach PO PDFs to emails
    - Track email delivery status
    - _Requirements: 8_
  
  - [ ] 16.3 Add advanced analytics dashboard
    - Add sales trend charts
    - Add stock level visualizations
    - Add vendor performance metrics
    - Add category analysis charts
    - _Requirements: 12_
  
  - [ ] 16.4 Optimize for mobile
    - Implement responsive layouts
    - Optimize table display for mobile
    - Add mobile-friendly navigation
    - _Requirements: 12_

## Notes

- **Status**: Production deployment complete with 45/57 tasks finished
- **Architecture**: 8 agents on AWS Bedrock AgentCore + 1 vendor caller on EC2
- **Models**: Nova Lite (7 agents), Nova Pro (1 agent), Nova Sonic (voice calls)
- **Data**: All prices stored in USD, converted to INR at display (rate: 89.6)
- **Transcripts**: Stored in-memory (Python dict) for demo, not DynamoDB
- **Authentication**: Not implemented for PoC/demo deployment
- **Testing**: Infrastructure planned but not yet implemented (Tasks 15.1-15.4)
- **Future Work**: User auth, email sending, analytics, mobile optimization (Task 16)

## Deployed Agent ARNs (Account 583880312323)

| Agent | ARN |
|-------|-----|
| Replenishment Planner | heartkart_replenishment_planner-XOV1Fs7FQg |
| Stockout Sentinel | heartkart_stockout_sentinel-SVao77AZkN |
| Inventory Copilot | heartkart_inventory_copilot-AqG2gM81So |
| Exception Investigator | heartkart_exception_investigator-JnGYePH7Ih |
| Markdown Coach | heartkart_markdown_coach-4VuN2TB1l4 |
| Market Intelligence | heartkart_market_intelligence-UV6jX76pJK |
| Pricing Intelligence | heartkart_pricing_intelligence-BpoKvYFNfq |
| Email Drafter | heartkart_email_drafter-l15N4AEAaF |
