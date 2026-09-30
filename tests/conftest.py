"""Test configuration.

The in-kernel tool packages (``orfb_tools``, ``graphormer_tools``,
``retrochimera_tools``, ``soltrannet_tools``, ``ezbattery_tools``) live under
``servers/<name>/<name>_tools/src`` with a src layout and are normally
pip-installed into each server's conda kernel. For the test suite we add their
``src`` directories to ``sys.path`` so they import directly without a separate
install step. These are inserted at the front so they take precedence over any
stale copy in site-packages.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_TOOL_SRC_DIRS = [
    _ROOT / "servers" / "provenance_tools" / "src",
    _ROOT / "servers" / "orfb" / "orfb_tools" / "src",
    _ROOT / "servers" / "graphormer" / "graphormer_tools" / "src",
    _ROOT / "servers" / "retrochimera" / "retrochimera_tools" / "src",
    _ROOT / "servers" / "soltrannet" / "soltrannet_tools" / "src",
    _ROOT / "servers" / "ezbattery" / "ezbattery_tools" / "src",
]

for _src in _TOOL_SRC_DIRS:
    path = str(_src)
    if path not in sys.path:
        sys.path.insert(0, path)
