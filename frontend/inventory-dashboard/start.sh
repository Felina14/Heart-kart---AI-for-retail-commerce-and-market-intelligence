#!/bin/bash

echo "Starting HeartKart Inventory Dashboard"
echo "=========================================="

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
fi

# Create .env.local if it doesn't exist
if [ ! -f ".env.local" ]; then
    echo "⚙️  Creating .env.local..."
    echo "NEXT_PUBLIC_API_URL=http://localhost:5000" > .env.local
fi

echo ""
echo "✅ Starting dashboard on http://localhost:3001"
echo "📊 Make sure backend is running on port 5000"
echo ""

npm run dev
