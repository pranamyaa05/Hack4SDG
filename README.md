# ReFit

Measured adaptations and repairs for everyday objects. Both tracks are implemented: flexible utensil-handle sleeves and light-duty drawer pulls with visible mounting holes.

The local app includes image intake, local/cloud AI adapters, manual confirmation, clarification questions, calibrated and manual measurement, CAD generation, fit coupons, output validation, downloads, saved designs, Re-fit, fit feedback, and a separate Statistics tab.

## Run on Windows

The current workspace already has an installed `.venv` and built frontend:

```powershell
.venv\Scripts\python -m tools.run
```

Open **http://127.0.0.1:8000/app/**. API documentation: http://127.0.0.1:8000/docs.
The app works through manual object selection without an AI provider.

For a fresh checkout (Node 22.12+ or 24 and Python 3.13 recommended):

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev,cad]"
npm.cmd ci --prefix frontend
npm.cmd run build --prefix frontend
.venv\Scripts\python -m tools.run
```

`requirements-dev.lock.txt` records the exact tested Python environment; use it to reproduce those versions before `pip install --no-deps -e .`. The frontend lockfile records npm dependencies.

## AI setup

Copy `.env.example` to `.env` and edit it. `tools.run` loads supported keys without evaluating shell code; existing environment variables take precedence.

For local vision, install Ollama separately and run `ollama pull qwen3-vl:4b`. The server URL is restricted to loopback; photos are never silently routed to a cloud fallback. See [the official model page](https://ollama.com/library/qwen3-vl:4b) for the current runtime requirements.

For Gemini, set `GEMINI_API_KEY` and `REFIT_GEMINI_MODEL` to a model supported by your account. Choose Gemini in the UI and consent to sending the resized photo and notes for that analysis. Provider credentials remain on the backend. Live model recognition has not been validated in this environment; no model or credentials were present.

## What the app produces

- Versioned specification and validation report.
- Validated solid STEP and watertight STL. STEP preserves solid geometry; the JSON specification drives regeneration, not a CAD feature-history tree.
- 10 mm fit coupons and tighter/looser variants for Adapt.
- Analytic SVG, PDF and PNG drawings, illustrative overlay or measured silhouette.
- Printable build card, including a foam-tube alternative for Adapt.
- Solid material estimate, explicit assumptions, artifact checksum manifest and ZIP package.

Repair uses confirmed through-bolts with external nuts; hidden-thread matching and strength certification are outside this release. Rigid sleeve materials are withheld until physical fit is validated; current Adapt generation uses TPU.

## Validation and honest limits

The tests cover structured provider requests using mocked HTTP, failure recovery, synthetic calibration, uncertainty propagation, persistent sessions, both real CAD pipelines, mesh properties, package checksums, downloads, feedback and Re-fit. Browser tests cover both manual workflows and the Statistics tab. See [delivery notes](docs/DELIVERY.md) for the latest check results.

**Physical measurement accuracy, real printed fit, material suitability and drawer load capacity remain unvalidated.** Test a coupon before a full sleeve. Reported fit feedback remains distinct from the immutable generated specification. Statistics do not equate generated files with successful repairs or inferred CO2 savings.

Your friend's landing page has not been supplied. The functional Studio lives at `/app/`; `/` redirects there until that landing page is integrated. No reference landing page was copied.

## Development

```powershell
.venv\Scripts\python -m pytest -q
npm.cmd run build --prefix frontend
npm.cmd test --prefix frontend
```

Browser tests use installed Google Chrome by default and an isolated database. Set `REFIT_TEST_BROWSER=msedge` for installed Edge, or install Playwright Chromium and set it to `chromium`. The test server uses port 8765.

For UI development, run the backend and `npm.cmd run dev --prefix frontend`; the Vite proxy forwards `/api` locally. SQLite and generated files live under `var/`, overridable with `REFIT_DATA_DIR`. Treat this as a single trusted local workspace. Public multiuser hosting needs authentication and per-user ownership checks before exposure.

See [measurement](docs/MEASUREMENT.md), [AI](docs/AI.md), [architecture](docs/ARCHITECTURE.md), [handoff](docs/HANDOFF.md), [deployment](docs/DEPLOYMENT.md), and the [roadmap](docs/ROADMAP.md).
ReForm3D remains isolated under `.references/` solely for inspiration. Its implementation and UI were not copied into this project.
