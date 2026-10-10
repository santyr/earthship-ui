"""Compatibility import for the shared deployable thermal runtime."""
import sys
from thermal_model import recent_cycles as _implementation
sys.modules[__name__] = _implementation
