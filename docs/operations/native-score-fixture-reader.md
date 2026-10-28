# Private retained-score fixture reader

The retained coordinator accepts an optional keyword-only `reader_factory` for
an explicit in-memory acquisition fixture. It passes the callable through
`run_retained_worker` and the retained runner to the existing reader-construction
point in `score_jobs`. It does not expose a CLI, environment, or configuration
override. Production callers omit it and retain the original closed reader
selection and source checks.

The callable receives the same closed reader configuration and
`shared_lock_guard` callback as the production constructor. That callback returns
the remaining original, nonrenewable deadline and still performs the existing
lock, pressure, source, and configuration checks. Model/context validation occurs
before acquisition. Supplying both a reader and a factory, a non-callable
factory, or an explicit factory returning no reader is refused.

Fixtures must retain the complete coordinator, query/receipt parsing, original
acquisition budget and pacing, source accounting, reports, independent equality,
and final custody checks. Synthetic readers and modeled transport/SQL do not
establish actual PostgreSQL, publication, sensor, or natural-score qualification.
The original actual historical workload remains a separate test.
