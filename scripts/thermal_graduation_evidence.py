"""Compatibility import for the shared deployable thermal runtime."""
import sys
from thermal_model import graduation_evidence as _implementation
sys.modules[__name__] = _implementation
