#!/bin/bash

echo "🚀 Starting Nova Sonic WebSocket Server (HeartKart Vendor Caller)"
echo "========================================"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    echo "📥 Installing dependencies..."
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

echo "✅ Starting WebSocket server on port 8080..."
echo ""
echo "📋 Next steps:"
echo "  1. In another terminal: ngrok http 8080"
echo "  2. Update NGROK_URL in .env"
echo "  3. Run: python3 make_conversational_call.py"
echo ""

python3 nova_sonic_twilio_server.py --websocket
