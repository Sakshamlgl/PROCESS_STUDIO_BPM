# Version 2.0 release

The engineering review, local operation and recovery workflows, UI redesign, input-dependent generation, source traceability, visual variants, modeler integration fixes and family-validation manifests are delivered together. See ENGINEERING_REVIEW.md for the findings addressed and VALIDATION.md for evidence and limits.

48 backend tests and 10 frontend/interoperability tests pass. The production frontend is prebuilt. Runtime data and credentials are excluded from the distributable archive; the current local workspace is retained separately on the user's machine. Three restorable example families are included under samples/.

Natural-language generation requires a user-configured model endpoint. No live model credentials or model weights are distributed. Structured generation, editing, variants, validation, simulation and recovery run locally without a model connection.
