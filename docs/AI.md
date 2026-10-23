# Object understanding and confirmation

The provider interface supports Ollama locally and Gemini through its generateContent endpoint. Neither adapter supplies measurements. Closed-schema analysis contains an object, component, qualitative confidence, cross-section guess, visible observations, separate inferences, and an optional reported functional difficulty. Unknown objects and extra fields are rejected.

1. POST /api/sessions/{id}/image: multipart image, expected_revision, user_text. JPEG/PNG is checked for size, resolution, brightness and detail. EXIF is stripped; the AI copy has a maximum 768-pixel long edge.
2. POST /api/sessions/{id}/analyze: expected_revision, optional provider, optional user_text and cloud_consent. Local inference is the default. Gemini requires explicit consent on each request; there is no automatic local-to-cloud fallback.
3. GET /api/sessions/{id}/analysis retrieves persisted analysis, questions and support status.
4. POST /api/sessions/{id}/confirm-object records corrected object_type, component, cross_section, handle_intact and confirmed_by_user true. Manual confirmation works without an image or model.
5. POST /api/sessions/{id}/answers fills the closed question slots. Adapt asks about functional difficulty and material preference; Repair asks about visible missing-pull mounting and surface condition. Already filled slots are not repeated. Unambiguous explicit user text can fill difficulty; ambiguous or negated text needs clarification. Model suggestions never become confirmed user answers.
6. POST /api/sessions/{id}/measurement/start continues only after the existing analysis workspace is supported and complete. The legacy direct manual measurement path still works for measurement-only sessions, but cannot generate a design without object/need confirmation.
7. POST /api/sessions/{id}/analysis/cancel with the current expected_revision invalidates an in-flight result and restores manual confirmation. This also recovers an interrupted run after a restart. A late response fails its revision check.

One process-local inference lock limits heavy inference to one active call. Provider timeouts are configurable. Schema-invalid output retries once; authorization, connectivity and rate-limit failures return the manual path without raw provider errors. All outputs still need user confirmation, including high-confidence classifications. No API key or provider response body is returned by status endpoints.

Supported Adapt scope: intact spoon, fork and knife handles only. Supported Repair scope: missing drawer pull, two visible mounting holes, intact mounting face. Other objects, food-contact targets, hidden mounting and structural damage are declined with an explanation.

## Configuration

REFIT_AI_PROVIDER: ollama, gemini or manual.
REFIT_OLLAMA_URL: loopback HTTP(S) URL, default http://127.0.0.1:11434.
REFIT_OLLAMA_MODEL: default qwen3-vl:4b.
REFIT_GEMINI_MODEL and GEMINI_API_KEY: optional cloud credentials; no cloud model ID is guessed.
REFIT_AI_TIMEOUT_SECONDS: default 45 seconds, configurable 1-120.

No model or API credentials were available during implementation. HTTP adapter behavior was tested with mock transports; live object/component recognition accuracy, model latency and GPU memory need evaluation on the actual runtime.

Technical references: [Ollama chat API](https://docs.ollama.com/api/chat), [structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [Qwen3-VL model](https://ollama.com/library/qwen3-vl:4b), [Gemini generateContent API](https://ai.google.dev/api/generate-content). Provider support does not imply a calibrated recognition-accuracy claim.
