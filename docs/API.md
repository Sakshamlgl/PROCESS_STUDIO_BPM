# API contract

Local JSON HTTP API. No CORS access is granted. Browser writes must originate from the loopback application or its local development port. Hosts are checked to resist DNS rebinding. No organizational identity/authentication is provided.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Version, schema and local mode |
| GET | `/api/families` | Library summary |
| GET | `/api/families/{id}` | Base, variants, conflicts, history, audit and trash |
| GET | `/api/families/{id}/backup` | Restorable v2 family envelope |
| GET | `/api/ai/status` | Configuration with credential values omitted |
| POST | `/api/ai/config` | Session model configuration |
| POST | `/api/ai/test` | Provider protocol smoke test |
| POST | `/api/generate` | Natural-language validated graph, evidence and XML preview |
| POST | `/api/compile` | Structured source or supported XML to graph/XML/analysis |
| POST | `/api/analyze` | Analysis of XML or graph |
| POST | `/api/families` | Create a family from reviewed source/XML |
| POST | `/api/preview-base` | Check proposed XML and identify variant conflicts without saving |
| POST | `/api/preview-variant` | Derive/analyze a recipe without saving |
| POST | `/api/save` | Save a new base revision |
| POST | `/api/variant` | Create a recipe-backed variant |
| POST | `/api/update-variant` | Update a variant using its version |
| POST | `/api/delete-variant` | Move a variant to recoverable trash |
| POST | `/api/restore-variant` | Restore a deleted variant |
| POST | `/api/restore` | Restore a historical base as a new revision |
| POST | `/api/release` | Validate all saved active models and produce an artifact manifest |
| POST | `/api/import-backup` | Restore a backup into a new family |

Writes use `Content-Type: application/json`. Body limit: 2 MB; backup restore: 10 MB. A family mutation requires `family` and current `revision`. Updating/deleting/restoring a variant also requires its `id` and current `version`. Read-modify-write actions use a SQLite `BEGIN IMMEDIATE` transaction and return after commit. Stale edits return 409 instead of overwriting newer work.

Recipe operations: `{id, action, target}` plus `name` for insert/modify, `after` for move, optional activity `type` and `role` for insert. Explicit operation IDs use letters, numbers and underscores. Inserted element ID is `Option_<operation id>`. Old positional-ID recipes remain readable for compatibility.

Errors include `error`, `code`, `requestId` and optional details. Representative codes: INVALID_INPUT, STALE_REVISION, STALE_VARIANT, DUPLICATE_NAME, NOT_FOUND, MODEL_NOT_CONFIGURED, MODEL_HTTP_ERROR, MODEL_UNREACHABLE, GENERATION_INVALID, HOST_REJECTED, ORIGIN_REJECTED, BODY_TOO_LARGE and DATABASE_BUSY. Provider errors never echo credentials or raw provider response bodies.

The backup format is `{format:"process-family-studio",version:2,family:{...}}`. Historical content is preserved, while import assigns fresh family/variant identifiers and revision numbering. Original v1 unwrapped family JSON is accepted when it contains a supported base XML document. Very large families should use `backend/manage.py backup` instead.
