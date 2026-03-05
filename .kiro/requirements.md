# Requirements Document

## Introduction

HeartKart AI Inventory Management System is an intelligent, AI-powered inventory management platform designed for seasonal retail businesses, with specialized focus on Valentine's Day retail. The system leverages AWS Bedrock AI agents to automate inventory planning, predict stockouts, detect anomalies, enable natural language queries, provide market intelligence, optimize pricing, and automate vendor communication via voice calls and email. The system transforms inventory management from a manual, reactive process into an intelligent, proactive system that anticipates needs, automates routine tasks, and provides actionable insights through conversational AI.

## Glossary

- **System**: The HeartKart AI Inventory Management System
- **AI_Agent**: Autonomous software component powered by AWS Bedrock that performs specific inventory management tasks
- **Inventory_Manager**: Primary user who manages inventory operations
- **Vendor**: External supplier who provides products
- **SKU**: Stock Keeping Unit - unique identifier for each product
- **ROP**: Reorder Point - stock level that triggers a purchase order
- **EOQ**: Economic Order Quantity - optimal order quantity that minimizes total inventory costs
- **Sales_Velocity**: Rate at which inventory is sold (units per day)
- **Stockout**: Situation where inventory reaches zero
- **PO**: Purchase Order - formal document sent to vendors to order products
- **DynamoDB**: AWS NoSQL database for product catalog, sales history, and call logs
- **Twilio**: Third-party service for voice calling
- **Nova_Sonic**: AWS Bedrock model for real-time bidirectional conversational AI
- **TwiML**: Twilio Markup Language for voice call scripting
- **Anomaly**: Unusual pattern in inventory data detected through statistical analysis
- **Z_Score**: Statistical measure of how many standard deviations a value is from the mean
- **Market_Intelligence**: Analysis of competitor pricing, regional demand, and category trends
- **Pricing_Intelligence**: Optimal pricing recommendations with guardrails and competitor comparisons
- **Guardrail**: Policy rule that enforces minimum margins and maximum discounts in pricing
- **AgentCore**: AWS Bedrock service for deploying and managing AI agents as containerized runtime endpoints
- **Strands**: AWS SDK framework for building AI agents with @tool decorators

## Requirements

### Requirement 1: Inventory Data Management

**User Story:** As an Inventory_Manager, I want to view and manage all inventory items in real-time, so that I can make informed decisions about stock levels.

#### Acceptance Criteria

1. WHEN the Inventory_Manager requests inventory data, THE System SHALL retrieve all products from DynamoDB (`valentines-products` table in cloud, `Products` table in local dev)
2. THE System SHALL display product information including SKU, name, category, vendor_name, vendor_phone, vendor_email, price, stock_quantity, sales_velocity, currency, delivery_options, and personalizable flag
3. WHEN inventory data is updated, THE System SHALL reflect changes in real-time across all interfaces
4. THE System SHALL support filtering and searching inventory by SKU, name, category, or vendor
5. THE System SHALL support 1,000+ SKUs (current catalog size) without performance degradation
6. THE System SHALL support multiple currencies with prices stored in USD and converted to INR (Indian Rupees) at display time using configurable exchange rate (default: 89.6)
7. THE System SHALL display Valentine's Day themed products including Artisanal Chocolates, Grooming Kits, Personalized Gifts, and Fashion Accessories

### Requirement 2: Automated Replenishment Planning

**User Story:** As an Inventory_Manager, I want automated purchase order recommendations based on stock levels and sales velocity, so that I can prevent stockouts and optimize order quantities.

#### Acceptance Criteria

1. WHEN stock_quantity falls below reorder_point, THE System SHALL generate a reorder recommendation
2. THE System SHALL calculate recommended_order_qty using simplified EOQ formula ensuring 30–60 days of stock, respecting vendor MOQ (minimum order quantity)
3. THE System SHALL classify urgency based on days_until_stockout:
   - CRITICAL: days_until_stockout ≤ 3
   - HIGH: days_until_stockout ≤ 7
   - MEDIUM: days_until_stockout ≤ 14
   - LOW: days_until_stockout > 14
4. WHEN generating recommendations, THE System SHALL group items by vendor for efficient ordering
5. THE System SHALL include vendor lead_time_days in reorder calculations
6. THE System SHALL calculate ROP = (sales_velocity × lead_time_days) + (sales_velocity × safety_stock_days)
7. THE System SHALL generate PO documents in PDF format with all order details
8. THE System SHALL calculate estimated_cost for each recommendation based on product price and quantity

### Requirement 3: Stockout Prediction and Prevention

**User Story:** As an Inventory_Manager, I want to predict stockouts before they occur and receive substitute product recommendations, so that I can maintain customer satisfaction and prevent lost sales.

#### Acceptance Criteria

1. THE System SHALL predict stockouts based on sales_velocity and current stock_quantity
2. WHEN a product is at risk of stockout, THE System SHALL calculate days_until_stockout = stock_quantity / sales_velocity
3. THE System SHALL assign risk_level based on days_until_stockout:
   - CRITICAL: days_until_stockout ≤ 3
   - HIGH: days_until_stockout ≤ 7
   - MEDIUM: days_until_stockout ≤ 14
   - LOW: days_until_stockout > 14
4. WHEN a stockout is predicted, THE System SHALL recommend substitute products from the same category
5. THE System SHALL match substitutes by category, color, and price_range (±20%)
6. THE System SHALL provide category-based risk analysis showing which product categories are most at risk

### Requirement 4: Natural Language Inventory Queries

**User Story:** As an Inventory_Manager, I want to query inventory data using natural language, so that I can get insights without needing SQL knowledge.

#### Acceptance Criteria

1. WHEN the Inventory_Manager submits a natural language query, THE System SHALL process it using AWS Bedrock Nova Lite via Strands @tool functions
2. THE System SHALL support search queries with filters (e.g., "Show me Valentine's gifts under ₹2000")
3. THE System SHALL support analytics queries (e.g., "What are my top 10 selling products?")
4. THE System SHALL support vendor-specific queries (e.g., "Which items from Artisan Chocolate Co are low in stock?")
5. THE System SHALL provide query suggestions and examples to guide users
6. WHEN a query cannot be understood, THE System SHALL provide helpful error messages and suggest alternative phrasings

### Requirement 5: Exception Detection and Investigation

**User Story:** As an Inventory_Manager, I want to automatically detect and investigate inventory anomalies, so that I can identify and resolve issues before they escalate.

#### Acceptance Criteria

1. THE System SHALL detect anomalies by splitting sales data into 80% historical and 20% recent windows
2. THE System SHALL calculate Z_Score = (recent_avg - historical_avg) / std_dev for informational context
3. THE System SHALL identify DEMAND_SURGE anomalies when recent_avg > historical_avg × threshold (default 1.5)
4. THE System SHALL identify DEMAND_DROP anomalies when recent_avg < historical_avg / threshold
5. THE System SHALL identify STAGNANT anomalies when recent_avg = 0 (while historical_avg > 0)
6. WHEN an anomaly is detected, THE System SHALL provide root cause analysis using AI_Agent
7. THE System SHALL provide actionable recommendations for each detected anomaly
8. THE System SHALL require minimum 5 days of sales data per SKU before analysis
9. THE System SHALL allow configurable analysis periods (default 30 days) and anomaly threshold (default 1.5 multiplier)
10. THE System SHALL assign severity: HIGH for DEMAND_SURGE with z_score > 3, MEDIUM otherwise

### Requirement 6: Clearance Strategy Optimization

**User Story:** As an Inventory_Manager, I want AI-powered clearance recommendations for aged inventory, so that I can optimize pricing and recover capital from slow-moving items.

#### Acceptance Criteria

1. THE System SHALL identify aged inventory based on configurable threshold (default 60 days)
2. WHEN aged inventory is identified, THE System SHALL recommend optimal markdown percentages
3. THE System SHALL provide phased clearance timeline with multiple markdown stages
4. THE System SHALL suggest product bundling strategies to move slow inventory
5. THE System SHALL project revenue recovery for each clearance strategy
6. THE System SHALL prioritize clearance items by urgency and potential revenue impact

### Requirement 7: Automated Vendor Communication via Voice Calls

**User Story:** As an Inventory_Manager, I want to automate vendor communication through AI-powered phone calls, so that I can save time and ensure consistent professional communication.

#### Acceptance Criteria

1. WHEN the Inventory_Manager initiates a vendor call, THE System SHALL generate an AI call script using AWS Bedrock Nova Lite
2. THE System SHALL support multiple call types: place_order, follow_up_late, check_availability
3. WHEN placing an order call, THE System SHALL include order_details, total_amount, and delivery_date in the script
4. THE System SHALL initiate real phone calls using Twilio integration
5. THE System SHALL use Amazon Nova Sonic for real-time bidirectional conversational AI during calls
6. THE System SHALL record all calls via Twilio
7. THE System SHALL capture call transcripts in-memory (Python dict keyed by call_sid) during the session
8. THE System SHALL analyze transcripts using AI to detect vendor YES/NO decisions
9. WHEN a vendor declines an order, THE System SHALL automatically try the next vendor in priority order
10. THE System SHALL store call metadata including vendor_name, phone_number, call_type, status, and duration
11. WHEN a call fails, THE System SHALL provide fallback to email communication

### Requirement 8: Automated Email Communication

**User Story:** As an Inventory_Manager, I want to automatically generate professional vendor emails with PO details, so that I can maintain consistent communication and documentation.

#### Acceptance Criteria

1. WHEN a vendor call is successful, THE System SHALL automatically draft a follow-up email
2. THE System SHALL generate professional emails using AWS Bedrock Nova Pro via AgentCore Runtime
3. THE System SHALL include PO details, order items, total_amount (converted to INR), and delivery_date in emails
4. WHEN a call transcript is available, THE System SHALL summarize key points in the email
5. THE System SHALL maintain context-aware tone and content based on vendor relationship
6. THE System SHALL allow the Inventory_Manager to review and edit emails before sending
7. THE System SHALL generate emails within a few seconds of request

### Requirement 9: Purchase Order Management

**User Story:** As an Inventory_Manager, I want to generate, track, and manage purchase orders, so that I can maintain organized procurement records.

#### Acceptance Criteria

1. WHEN a PO is created, THE System SHALL assign a unique po_number in format "PO-YYYYMMDD-HHMMSS"
2. THE System SHALL generate PO documents in PDF format with all order details
3. THE System SHALL include vendor information, items, quantities, prices (in INR), and delivery dates in POs
4. THE System SHALL store PO PDFs in generated_pos/ directory for retrieval
5. THE System SHALL track PO status (pending_email, email_sent)
6. WHEN a PO email is sent, THE System SHALL update status to email_sent
7. THE System SHALL provide API endpoint to retrieve PO PDFs by po_number
8. THE System SHALL maintain order history with all PO details and associated call information (in-memory)

### Requirement 10: Multi-Vendor Orchestration with Fallback

**User Story:** As an Inventory_Manager, I want the system to automatically try multiple vendors in priority order when placing orders, so that I can ensure orders are fulfilled even if the preferred vendor declines.

#### Acceptance Criteria

1. WHEN placing an order, THE System SHALL query vendors by product category from DynamoDB
2. THE System SHALL try vendors in priority order starting with preferred_vendor_name if provided
3. WHEN a vendor declines (says NO), THE System SHALL automatically call the next vendor in priority order
4. THE System SHALL analyze call transcripts using AI to detect YES/NO decisions
5. WHEN a vendor accepts (says YES), THE System SHALL generate PO and draft email
6. WHEN all vendors decline, THE System SHALL create notification for manual intervention
7. THE System SHALL store all call attempts with vendor names, decisions, and transcripts
8. THE System SHALL return final status indicating success or failure with all attempt details

### Requirement 11: Real-Time Call Streaming with Nova Sonic

**User Story:** As an Inventory_Manager, I want AI-powered real-time conversational calls with vendors, so that the system can handle dynamic conversations and respond appropriately to vendor questions.

#### Acceptance Criteria

1. WHEN a call is initiated, THE System SHALL establish WebSocket connection between Twilio and Nova Sonic via EC2 server
2. THE System SHALL stream audio bidirectionally between caller and Nova Sonic in real-time
3. THE System SHALL handle audio encoding/decoding between Twilio format (μ-law 8kHz) and Nova Sonic format (PCM 16kHz)
4. THE System SHALL provide vendor context to Nova Sonic including vendor_name, contact_person, and order_details
5. THE System SHALL configure Nova Sonic with appropriate system prompt for professional vendor communication
6. THE System SHALL maintain conversation history throughout the call
7. WHEN the call ends, THE System SHALL store complete conversation transcript (in-memory)
8. THE System SHALL handle connection errors gracefully with logging

### Requirement 12: Dashboard and User Interface

**User Story:** As an Inventory_Manager, I want a comprehensive dashboard to access all AI agents and view inventory insights, so that I can manage operations from a single interface.

#### Acceptance Criteria

1. THE System SHALL provide a web-based dashboard accessible via the browser (Next.js on localhost:3001)
2. THE System SHALL display real-time inventory table with search and filter capabilities
3. THE System SHALL provide collapsible panels for each AI_Agent
4. THE System SHALL display replenishment recommendations with urgency indicators
5. THE System SHALL display stockout predictions with risk levels and substitute suggestions
6. THE System SHALL provide natural language query interface with example queries
7. THE System SHALL display exception reports with anomaly types and recommendations
8. THE System SHALL display clearance recommendations with markdown strategies
9. THE System SHALL display order history with PO details and status
10. THE System SHALL provide action buttons for common tasks (call vendor, export PO, send email)
11. THE System SHALL display market intelligence and pricing intelligence panels
12. THE System SHALL be functional on desktop browsers

### Requirement 13: API and Integration Architecture

**User Story:** As a developer, I want a well-structured REST API with clear endpoints, so that I can integrate the system with other tools and extend functionality.

#### Acceptance Criteria

1. THE System SHALL provide REST API with JSON response format
2. THE System SHALL include standard response structure with success (boolean), data (object), error (string if error), and timestamp (ISO 8601) fields
3. THE System SHALL provide health check endpoint (GET /api/health) returning service status
4. THE System SHALL provide CORS support for cross-origin requests
5. THE System SHALL handle errors gracefully with appropriate HTTP status codes
6. THE System SHALL log all API requests and errors for debugging (via Python print/logging)
7. THE System SHALL support serverless deployment on AWS Lambda (via serverless-wsgi)

### Requirement 14: Data Storage and Retrieval

**User Story:** As a system administrator, I want reliable data storage with fast retrieval, so that the system can handle large inventories and maintain performance.

#### Acceptance Criteria

1. THE System SHALL store product catalog in DynamoDB (`valentines-products` table) for fast retrieval
2. THE System SHALL store sales history in DynamoDB (`SalesHistory` table) for anomaly detection
3. THE System SHALL store call logs in DynamoDB (`heartkart-call-logs` table) for vendor communication tracking
4. THE System SHALL store PO PDFs in generated_pos/ directory
5. THE System SHALL support 1,000+ SKUs in DynamoDB without performance degradation
6. THE System SHALL retrieve product data from DynamoDB with standard DynamoDB latency
7. THE System SHALL handle concurrent read/write operations through DynamoDB's built-in concurrency model

### Requirement 15: Security and Access Control

**User Story:** As a system administrator, I want secure access control and data protection, so that sensitive inventory and vendor information is protected.

#### Acceptance Criteria

1. THE System SHALL use IAM role-based access control for AWS services
2. THE System SHALL store Twilio credentials securely in environment variables (not in code)
3. THE System SHALL provide .env.example files documenting required variables without exposing actual values
4. THE System SHALL use .gitignore to prevent committing .env files, credentials, and secrets
5. THE System SHALL not log or expose sensitive credentials in error messages
6. THE System SHALL not implement user authentication for PoC/demo deployment (AWS Cognito planned for future production deployment)

### Requirement 16: Performance Goals

**User Story:** As a system administrator, I want the system to handle the current inventory and user load efficiently.

#### Acceptance Criteria

1. THE System SHALL support 1,000+ SKUs without performance degradation
2. THE System SHALL process AI agent queries via AWS Bedrock within reasonable timeframes
3. THE System SHALL load the dashboard within a few seconds
4. THE System SHALL support serverless scaling via AWS Lambda for the cloud deployment

### Requirement 17: Logging and Observability

**User Story:** As a system administrator, I want logging for troubleshooting, so that I can diagnose issues.

#### Acceptance Criteria

1. THE System SHALL log all API requests with endpoint and response status (via Python print statements)
2. THE System SHALL log all AI agent invocations with model and response summary
3. THE System SHALL log all Twilio call events with call_sid, status, and duration
4. THE System SHALL log all errors with stack traces for debugging

### Requirement 18: Cost Optimization

**User Story:** As a business owner, I want the system to operate cost-effectively, so that I can maximize ROI while maintaining functionality.

#### Acceptance Criteria

1. THE System SHALL use AWS Bedrock Nova Lite (`amazon.nova-lite-v1:0`) for 7 of 9 AI agents to minimize costs
2. THE System SHALL use AWS Bedrock Nova Pro (`amazon.nova-pro-v1:0`) only for Email Drafter where professional writing quality is required
3. THE System SHALL use Amazon Nova Sonic (`amazon.nova-sonic-v1:0`) for real-time vendor voice calls
4. THE System SHALL use serverless architecture (Lambda) for cloud deployment to pay only for actual usage
5. THE System SHALL use DynamoDB on-demand pricing for variable workloads

### Requirement 19: Error Handling and Resilience

**User Story:** As an Inventory_Manager, I want the system to handle errors gracefully and provide helpful feedback, so that I can understand issues and take corrective action.

#### Acceptance Criteria

1. WHEN an API request fails, THE System SHALL return appropriate HTTP status code and error message in standard JSON format
2. WHEN an AI agent fails, THE System SHALL return error details to the frontend for display
3. WHEN Twilio is not configured, THE System SHALL return clear error message indicating missing credentials
4. WHEN a vendor call fails, THE System SHALL provide fallback to email communication
5. THE System SHALL log all errors with sufficient context for debugging

### Requirement 20: Testing and Quality Assurance

> **Note**: Testing infrastructure is planned for future implementation. No test files currently exist in the codebase.

**User Story:** As a developer, I want comprehensive testing coverage, so that I can ensure system reliability and catch bugs before production.

#### Acceptance Criteria (Planned)

1. THE System SHOULD include unit tests for core functions (pytest for Python, Jest for TypeScript)
2. THE System SHOULD include integration tests for API endpoints
3. THE System SHOULD validate AI agent responses for quality and accuracy
4. THE System SHOULD test error handling and edge cases
5. THE System SHOULD achieve >80% code coverage target

### Requirement 21: Market Intelligence Analysis

**User Story:** As an Inventory_Manager, I want market intelligence insights including competitor pricing and regional demand trends, so that I can make data-driven pricing and inventory decisions.

#### Acceptance Criteria

1. THE System SHALL provide Competitor Price Index Analysis showing price comparisons across competitors
2. THE System SHALL provide Regional Demand Trend Analysis showing demand patterns by geographic region
3. THE System SHALL provide Category Trend Signals showing market trends by product category
4. THE System SHALL support full market intelligence reports combining all analysis types
5. THE System SHALL support filtered reports by report_type (competitor, regional, category)
6. THE System SHALL support category-specific and region-specific queries
7. THE System SHALL use AWS Bedrock Nova Lite with Strands framework for market analysis
8. THE System SHALL provide AI-powered insights and recommendations based on market data

### Requirement 22: Pricing Intelligence and Optimization

**User Story:** As an Inventory_Manager, I want optimal pricing recommendations with guardrails and competitor comparisons, so that I can maximize profit while remaining competitive.

#### Acceptance Criteria

1. THE System SHALL calculate recommended price ranges with guardrails including min_margin_percent and max_discount_percent
2. THE System SHALL enforce default min_margin_percent of 15% to prevent margin erosion
3. THE System SHALL enforce default max_discount_percent of 40% to maintain brand value
4. THE System SHALL apply category-specific overrides:
   - Premium Categories (Premium Gifts, Luxury Items, Designer Collection): min_margin 25%, premium_price_max_multiplier 2.0
   - Budget Categories (Gifts Under ₹499, Budget Items): min_margin 10%, max_discount 50%
5. THE System SHALL provide Competitor Price Comparison showing how product prices compare to competitors
6. THE System SHALL calculate Demand Impact Analysis using price elasticity (budget: -2.5, mid-range: -1.8, premium: -1.2)
7. THE System SHALL provide Price Optimization Recommendations prioritized by revenue impact
8. THE System SHALL support full pricing intelligence reports combining all analysis types
9. THE System SHALL support filtered analysis by analysis_type (price_range, competitor_comparison, demand_impact, optimization)
10. THE System SHALL support both SKU-level and category-level pricing analysis
11. THE System SHALL use AWS Bedrock Nova Lite with Strands framework for pricing analysis
12. THE System SHALL project revenue impact for each pricing recommendation
