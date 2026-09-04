"""Combined test runner for Google Sheets handler and writer tests.

Aliases tests from test_sheets_handler and test_sheets_writer to support
the exact command specified in implementation_plan_v4.md:
`python -m pytest tests/test_sheets.py`
"""

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from test_sheets_handler import *  # noqa: F401, F403
from test_sheets_writer import *  # noqa: F401, F403
