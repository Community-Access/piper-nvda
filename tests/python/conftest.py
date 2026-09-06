"""pytest configuration: install NVDA API stubs and the gettext builtin so the
addon modules import outside NVDA, and put the addon package on sys.path."""

import builtins
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# gettext underscore that NVDA installs as a builtin.
if not hasattr(builtins, "_"):
    builtins._ = lambda s: s

# Make `synthDrivers.piper` and `globalPlugins.piperManager` importable
# from the addon tree.
sys.path.insert(0, os.path.join(ROOT, "addon"))
# Make the stub NVDA modules importable (lower priority than real ones would
# be inside NVDA, but here there are no real ones).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "nvda_stubs"))
