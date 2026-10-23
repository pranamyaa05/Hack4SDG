# Design contract 1.0.0

`backend/contracts.py` is the source for `schemas/design-spec-v1.schema.json`.
`sample_data/` contains two illustrative specifications, one per track, plus a manifest with their content hashes. These are contract fixtures, not fabricated or measured parts.

Units: mm. Local coordinates: x length, y width, z thickness; sleeve slit on +z; origin at centre of start face. Drawer mounting centres will be specified in the geometry chunk before teammate integration.

Sleeve clearance is the TOTAL addition to each measured inner span, not radial clearance. Covered length is a critical measurement. Pull mounting-hole diameter is required separately from centre spacing; hidden screw threads are unsupported.

`content_hash()` hashes sorted compact UTF-8 JSON excluding created_at; numeric precision is preserved. This explicitly supersedes the blueprint's four-decimal rounding. The hash is stored in an external manifest, preventing self-reference. Artifact SHA-256 entries will be added only when actual files exist.

Verification is limited by the weakest critical measurement. A concept may carry provisional parameters for illustration, but must never be routed to dimensioned CAD export. Physical evidence recorded by a user is a declaration, not independently certified metrology.

Future complete packages include design_spec.json, manifest.json, validation_report.json, actual STEP/STL and coupon files, drawings, overlay, build_card.pdf, and impact_ledger.json. Every artifact will reference the spec hash. Fixture manifests currently contain only the spec and its hash.
