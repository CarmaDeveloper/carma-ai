"""Application starter with database initialization."""

import os
import sys

import uvicorn

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.logging import setup_logger

logger = setup_logger(__name__)

if __name__ == "__main__":
    # Start the app
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
