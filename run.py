import os
import sys
import uvicorn

# Ensure repository root is in python path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

if __name__ == "__main__":
    print("================================================================")
    print("  Stock Pro India AI Terminal - Enterprise Desktop Engine")
    print("  Localhost Terminal UI : http://127.0.0.1:8000")
    print("  API Documentation     : http://127.0.0.1:8000/docs")
    print("================================================================")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False, log_level="info")
