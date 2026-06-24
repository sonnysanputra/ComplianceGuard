"""
Run the CompliGuard API server.

  cd backend
  python server.py

Then open http://localhost:8000/docs for interactive API testing.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.api.routes:app", host="0.0.0.0", port=8000, reload=True)
