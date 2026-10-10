"""Compatibility exports; registration executes in the pinned score-input module."""
from .installed_shade_score_inputs import (
    register_compressed_publication_jobs, resolve_registered_score_queue,
    REGISTRATION_SCHEMA as SCHEMA, REGISTRATION_HORIZONS as HORIZONS,
    REGISTRATION_SITE as SITE,
)
