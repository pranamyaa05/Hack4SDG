# Paused handoff - 23 October 2026

Paused at the user's request after completing the form-label accessibility fix and its verification. Do not start another task until asked to continue.

## Verified checkpoint

- Backend: 67 tests pass. One upstream Starlette/httpx deprecation warning remains.
- Browser: all 3 workflows pass after the label fix: Adapt through package download, feedback, Statistics and Re-fit with changed need; Repair through confirmed hardware and CAD generation plus mobile layout; desktop presentation.
- Production frontend: TypeScript check and Vite build pass.
- Python lint/format checks passed before the last test run.
- The temporary browser-test server was stopped. No production server was started.

## Implemented

FastAPI/SQLite foundation; local Ollama and optional Gemini adapters with manual fallback; object confirmation and clarification; manual/photo/paper-strip measurement; both deterministic CAD engines; checked STEP/STL and Adapt coupons; drawings, overlays, build cards and material estimates; checksum ZIP packages; React Studio at /app/ with 3D viewing, saved designs, Re-fit and a separate Statistics tab.

The existing landing page is still pending from the user's friend. ReForm3D remains isolated under .references/ and was used only for inspiration.

## Continue here next time

1. Finish release/handoff documentation: docs/ROADMAP.md and some architecture/handoff notes still describe earlier chunks. Document manufacturing schema 1.1 alongside the preserved 1.0 fixture contract.
2. Regenerate the checked-in Fit Sheet PDF/preview from the updated generator: the generator now explains cutting a drawer-hole window, but docs/assets still contains the earlier PDF text.
3. Run tools.generate_examples and inspect the explicitly illustrative packages/drawings/build cards. The script exists but has not been run. Check the added 1:1 guides visually.
4. Refresh requirements-dev.lock.txt; the current snapshot predates CAD and Ruff installation. The frontend package-lock.json is current.
5. Check the final deployment recipe and launcher. Dockerfile is supplied but has not been built or run. Public hosting is not authorized or configured as a multiuser service.
6. Add live AI configuration/benchmarking when Ollama or credentials become available. Provider tests use mock HTTP; no live recognition accuracy is claimed.
7. Collect physical ruler/caliper reference data and coupon/load trials. No physical accuracy, fit, material suitability, or load capacity is validated.
8. Integrate the friend's landing page when provided; retain the separate Statistics navigation tab.

## Local commands

Start: .venv/Scripts/python -m tools.run (http://127.0.0.1:8000/app/)
Backend tests: .venv/Scripts/python -m pytest -q
Frontend build: npm.cmd run build --prefix frontend
Browser tests: npm.cmd test --prefix frontend

Browser tests use installed Chrome, an isolated database under var/browser-tests-*, and port 8765. On this Windows runner the Playwright test-server teardown can hang after all tests pass; stop only the specific server process started by that run if needed. Test databases do not populate the production workspace.
