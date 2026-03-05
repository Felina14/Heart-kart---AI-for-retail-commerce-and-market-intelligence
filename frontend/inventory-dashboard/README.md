# HeartKart Inventory Dashboard

Admin dashboard for managing Valentine's product inventory with AI-powered vendor calling.

## Features

### ✅ Current Features
- **Real-time Inventory Tracking** - View all products with stock levels
- **Stats Overview** - Total products, low stock alerts, inventory value
- **Low Stock Alerts** - Automatic alerts for items below reorder point
- **Vendor Management** - Track vendor information for each product
- **Product Management** - Update stock levels and reorder points

### 🚀 AI Features (Ready for Implementation)
- **AI Vendor Calling** - Automated calls to vendors when stock is low
- **Smart Reordering** - AI determines optimal reorder quantities
- **Conversation Logs** - Track all AI-vendor interactions
- **Auto-approval** - Set thresholds for automatic order placement

## Project Structure

```
inventory-dashboard/
├── app/
│   ├── page.tsx          # Main dashboard page
│   └── layout.tsx        # Root layout
├── components/
│   ├── DashboardHeader.tsx    # Top navigation bar
│   ├── StatsOverview.tsx      # Statistics cards
│   ├── InventoryTable.tsx     # Main inventory table
│   ├── LowStockAlerts.tsx     # Alert sidebar
│   └── AIVendorPanel.tsx      # AI calling interface
├── package.json
├── tsconfig.json
└── next.config.js
```

## Installation

### 1. Install Dependencies
```bash
cd inventory-dashboard
npm install
```

### 2. Configure Environment
Create `.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:5000
```

### 3. Start Dashboard
```bash
npm run dev
```

Dashboard will run on: **http://localhost:3001**

## Usage

### Access Dashboard
1. Start backend: `python3 app.py` (port 5000)
2. Start dashboard: `npm run dev` (port 3001)
3. Open: http://localhost:3001

### Features

#### Stats Overview
- Total Products
- Low Stock Items
- Out of Stock Items
- Total Inventory Value

#### Inventory Table
- View all products
- See stock levels
- Check vendor information
- Manage individual items
- Color-coded status indicators

#### Low Stock Alerts
- Real-time alerts for low stock
- Out of stock warnings
- Click to manage product

#### AI Vendor Panel
1. Select a product from table or alerts
2. Click "Initiate AI Call to Vendor"
3. Watch AI conversation in real-time
4. Order automatically placed

## API Endpoints

### Get Inventory
```
GET /inventory
Response: { success: true, inventory: [...], count: 123 }
```

### Update Inventory
```
PUT /inventory/<sku>
Body: { stock_quantity: 50, reorder_point: 20, vendor: "ABC Corp" }
Response: { success: true, message: "Inventory updated" }
```

## Components

### DashboardHeader
- Navigation bar
- Reports and settings buttons
- Branding

### StatsOverview
- 4 stat cards
- Real-time calculations
- Color-coded indicators

### InventoryTable
- Sortable columns
- Stock status badges
- Manage buttons
- Refresh functionality

### LowStockAlerts
- Filtered alerts
- Click to select
- Priority indicators

### AIVendorPanel
- Product details
- AI call button
- Conversation log
- Status indicators

## AI Vendor Calling (Future Implementation)

### Phase 1: Manual Triggering ✅
- Select product
- Click to initiate call
- View conversation log

### Phase 2: Automatic Triggering
- Monitor stock levels
- Auto-call when critical
- Email notifications

### Phase 3: Smart Ordering
- AI determines quantity
- Price negotiation
- Multi-vendor comparison

### Phase 4: Full Automation
- Auto-approve orders
- Track deliveries
- Update inventory automatically

## Customization

### Colors
Edit component styles to match your brand:
- Primary: `#E11D48` (Red)
- Secondary: `#8B5CF6` (Purple)
- Success: `#10B981` (Green)
- Warning: `#F59E0B` (Orange)
- Danger: `#EF4444` (Red)

### Thresholds
Adjust in components:
- Low stock: `stock_quantity <= reorder_point`
- Out of stock: `stock_quantity === 0`

## Development

### Add New Component
```bash
# Create component
touch components/NewComponent.tsx

# Import in page.tsx
import NewComponent from '../components/NewComponent'
```

### Add New Feature
1. Create component in `components/`
2. Import in `app/page.tsx`
3. Add to layout
4. Connect to API

## Deployment

### Build for Production
```bash
npm run build
npm start
```

### Environment Variables
```
NEXT_PUBLIC_API_URL=https://your-api.com
```

## Next Steps

1. **Test Dashboard** - View inventory data
2. **Implement AI Calling** - Connect to voice API
3. **Add Vendor Management** - CRUD for vendors
4. **Add Reports** - Analytics and insights
5. **Add Notifications** - Email/SMS alerts

## Support

For issues or questions:
- Check backend is running on port 5000
- Verify API endpoints are accessible
- Check browser console for errors
- Ensure products have vendor information

---

**Status**: ✅ UI Complete, Ready for AI Integration  
**Port**: 3001  
**Backend**: Port 5000  
**Next**: Implement AI vendor calling logic
