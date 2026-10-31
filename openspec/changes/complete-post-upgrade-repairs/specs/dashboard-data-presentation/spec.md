# Dashboard data presentation

## Purpose

Present current household observations and energy information clearly after the
upgrade while retaining the user's approved tablet layout.

## ADDED Requirements

### Requirement: Requested clock and energy layout is preserved
The Home view SHALL keep the small date at the far left before Suggestions,
the temperature-sized time on the left of the energy display, and Today on its
own line below the power figures, retaining all original labels and values.

#### Scenario: Home is viewed on the landscape tablet
- **WHEN** Home renders at the supported landscape sizes
- **THEN** time matches the temperature text size, the energy display remains
  to its right, each energy row is unbroken, and the values fit without clipping

### Requirement: UI receives the live OpenHAB data stream
The deployed UI SHALL load valid connection configuration and reconcile current
OpenHAB items rather than displaying pages with missing data after a release.

#### Scenario: A UI release starts
- **WHEN** a browser loads the deployed release
- **THEN** connection configuration loads as JSON and the UI reaches live,
  reconciled state with the expected items and no browser read failures

### Requirement: Analytics preserves source meaning
The dashboard SHALL distinguish current, remaining-day, full-day, and next-day
products using their original producer, accounting, confirmation, and expiry
provenance while preserving stored history.

#### Scenario: A forecast product is unavailable
- **WHEN** a required source product is missing, invalid, or expired
- **THEN** analytics reports the degraded condition without presenting unrelated
  legacy values or older forecasts as a current product

### Requirement: All supported routes work after recovery
The repaired UI SHALL load the supported Home, Energy, Weather, Earthship,
Shades, and Controls routes with the expected current data and usable layout.

#### Scenario: The final read-only browser audit runs
- **WHEN** the deployed routes are checked at their supported viewport sizes
- **THEN** the views have no unexplained missing data, failed reads, or runtime
  errors and the audit triggers no equipment commands
