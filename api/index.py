import os
import sys
from pathlib import Path

# Ensure project root is in sys.path for Vercel
root_dir = Path(__file__).parent.parent.resolve()
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.web.server import app
