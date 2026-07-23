"""SAR File Analyzer REST API.

Importing this package sets up sys.path/env so the reusable modules in
``code/`` (polars parsing, chart builders, sqlite metadata) can be imported
headlessly, i.e. without a running Streamlit session.
"""

from . import bootstrap  # noqa: F401  (must run before any code/ import)
