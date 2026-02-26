#!/bin/bash
cd /root/vless-vpn-bot

# Запуск FastAPI
cd /root/vless-vpn-bot
python3 -c "
import sys
sys.path.insert(0, '.')
from api.main import app
import uvicorn
uvicorn.run(app, host='0.0.0.0', port=3000)
"
