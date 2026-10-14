# Retained scorer failure diagnostics

Scheduled legacy and historical scoring failed with only `score_withheld`, while
current-model scoring could complete. The previous log did not establish whether
resource admission, unavailable inputs, or another validation caused the failure.

The score coordinator now reports a fixed, bounded reason category. Raw exception
messages, paths, connection details and traceback text are never added to its
failure output. Unknown validation errors remain `validation_refused`.

Retained legacy and native scorers execute their original `run()` function from
the pinned source archive. The current wrapper formats their failures. Python's
`-P` option and explicit archived PYTHONPATH prevent current dependencies from
replacing archived dependencies. The wrapper checks the deployment digest, source
digest, dependency context and unchanged source/manifest around execution.
Original model validation, resource guards, scoring and report writes remain in
the retained function. Busy responses still return status 75.

Validation: 39 focused tests passed in 1.89 seconds, covering current CLI reason
categories, private-error suppression, original legacy/native function arguments,
source and manifest drift, dependency separation in a real Python child, and both
legacy and native dispatch commands. An existing deadline regression now derives
its expiration from the deployed 120-second constant instead of assuming 50 seconds.

Deployment is pending. This change does not establish the cause of historical
failures, alter resource policy, train a model, or establish forecast accuracy.
