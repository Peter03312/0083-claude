#!/usr/bin/env python3
"""生产/本地启动入口。"""
import os

from app.server import app

if __name__ == "__main__":
    port = int(os.environ.get("API_PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
