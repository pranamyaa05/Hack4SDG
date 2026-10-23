# Architecture decisions

- FastAPI orchestrates typed stage services. SQLite persists sessions with revision checks to prevent stale updates.
- Adapt and Repair share intake, measurement provenance, exports, and a discriminated design contract. Family-specific parameters remain separate.
- AI interprets objects and reported difficulty. Calibrated CV or user measurements provide dimensions; deterministic rules generate geometry.
- Unknown/conflicting dimensions cannot support dimensioned export. Cross-checked means distinct methods; physical verification requires confirmed physical evidence.
- No public endpoint allows arbitrary workflow transitions. Future stage endpoints must validate their exit conditions before using the internal transition function.
- Re-fit creates a new design linked by parent_design_id. Original designs remain unchanged.
- Model providers sit behind an interface in Chunk 3; local/cloud configuration never changes measurement requirements.
- Keep CAD isolated from the API runtime if its supported Python version differs. Benchmark and test real dependencies before pinning the geometry environment.
- Frontend setup waits for the existing landing page source. Do not replace the supplied design.
- Statistics must distinguish attempts, generated designs, confirmed use, and physical fit trials. Counts of generated files are not successful repairs.
- Initial API is for a trusted local machine. Authentication, ownership checks, upload isolation, and deployment hardening precede public hosting.

## Current API

POST /api/sessions requires track and explicit consent; GET /api/sessions/{uuid} retrieves a session.
GET /api/health reports only implemented capabilities; GET /api/contracts/design-spec serves the versioned JSON Schema.

## Contract lifecycle

Pydantic models generate the checked-in schema and illustrative samples. Contract changes require review of both tracks, fixtures, and compatibility; breaking changes require a new schema version. Before CAD integration, freeze the geometry conventions with the teammate.
