"""Environment bootstrap for headless (non-Streamlit) use of the code/ modules.

Has to be imported before any module from code/ is imported:
- puts code/ on sys.path (the app modules use flat imports like ``import helpers_pl``)
- anchors UPLOAD_DIR to an absolute path so the API does not depend on the
  current working directory (streamlit is normally started from code/)
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CODE_DIR = REPO_ROOT / "code"

if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

# Same effective default as running streamlit from code/ (upload -> code/upload)
os.environ.setdefault("UPLOAD_DIR", str(CODE_DIR / "upload"))
