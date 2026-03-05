#!/bin/bash

echo "Setting up HeartKart Inventory Dashboard..."
echo ""

cd "$(dirname "$0")"

echo "📦 Installing dependencies..."
npm install

echo ""
echo "✅ Setup complete!"
echo ""
echo "To start the dashboard:"
echo "  cd inventory-dashboard"
echo "  npm run dev"
echo ""
echo "Dashboard will run on: http://localhost:3001"
