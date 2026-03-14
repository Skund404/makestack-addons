"""pytest configuration for kitchen module tests.

Adds makestack-shell to sys.path so that makestack_sdk and backend.sdk
resolve correctly. The kitchen module root is kept off sys.path to prevent
backend/__init__.py from shadowing the shell's backend namespace package.

Python adds '' (CWD) to sys.path when invoked as `python3 -m pytest`. When
CWD is the kitchen module root, this puts backend/__init__.py ahead of the
shell's backend namespace package. We remove '' (and any path that resolves
to the kitchen root) here, before any SDK imports occur.

--import-mode=importlib (set in pyproject.toml) ensures pytest itself does
not re-add the kitchen root. Kitchen code (migrations etc.) is loaded via
importlib by absolute file path, so it never needs to be on sys.path.

Run from the kitchen module directory:
    cd makestack-addons/modules/kitchen
    python3 -m pytest
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_KITCHEN_ROOT = os.path.dirname(_HERE)
_SHELL_ROOT = os.path.normpath(os.path.join(_KITCHEN_ROOT, "..", "..", "..", "makestack-shell"))
_kitchen_root_resolved = os.path.realpath(_KITCHEN_ROOT)

# Remove '' (CWD) and any entry that resolves to the kitchen module root.
sys.path = [
    p for p in sys.path
    if os.path.realpath(p or os.getcwd()) != _kitchen_root_resolved
]

if _SHELL_ROOT not in sys.path:
    sys.path.insert(0, _SHELL_ROOT)
