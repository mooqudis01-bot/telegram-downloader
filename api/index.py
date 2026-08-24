import os
import sys
import traceback
from pathlib import Path

# Add project root to sys.path for Vercel Serverless Function
base_dir = Path(__file__).parent.parent.resolve()
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

try:
    from app.web.server import app
except Exception as e:
    tb = traceback.format_exc()
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    app = FastAPI()
    
    @app.get("/{full_path:path}", response_class=HTMLResponse)
    async def error_page(full_path: str = ""):
        return HTMLResponse(
            content=f"<h2>Vercel Startup Exception</h2><pre>{tb}</pre>",
            status_code=500
        )

__all__ = ["app"]
