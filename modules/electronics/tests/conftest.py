"""pytest configuration for electronics module tests.

Adds makestack-shell to sys.path so that makestack_sdk and backend.sdk
resolve correctly. The module root is kept off sys.path to prevent
backend/__init__.py from shadowing the shell's backend namespace package.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_ROOT = os.path.dirname(_HERE)
_SHELL_ROOT = os.path.normpath(os.path.join(_MODULE_ROOT, "..", "..", "..", "makestack-shell"))
_module_root_resolved = os.path.realpath(_MODULE_ROOT)

# Remove '' (CWD) and any entry that resolves to the module root.
sys.path = [
    p for p in sys.path
    if os.path.realpath(p or os.getcwd()) != _module_root_resolved
]

if _SHELL_ROOT not in sys.path:
    sys.path.insert(0, _SHELL_ROOT)
