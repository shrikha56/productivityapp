#!/bin/bash
# Run Signal locally
cd "$(dirname "$0")"
if [ ! -d "venv" ]; then
  echo "Creating venv..."
  python3 -m venv venv
fi
source venv/bin/activate
pip install -q python-dotenv flask supabase openai
# Free port 5001 if a previous run is still active
if lsof -ti :5001 >/dev/null 2>&1; then
  echo "Stopping process on port 5001..."
  lsof -ti :5001 | xargs kill -9 2>/dev/null || true
  sleep 1
fi
echo "Signal running at http://127.0.0.1:5001/"
python server.py
