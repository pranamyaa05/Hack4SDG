# Running and packaging

## Tested local path

Build the frontend with npm.cmd run build --prefix frontend, then launch .venv/Scripts/python -m tools.run. It serves the API and Studio from the same origin, bound to 127.0.0.1:8000. The root redirects to /app/ while the existing landing page is pending. The app requires one trusted local operator; authentication and user ownership isolation are not implemented.

Persist the directory selected by REFIT_DATA_DIR. It contains refit.sqlite3 and designs/{uuid}/ packages. Back up both the database and designs together while the server is stopped. Session identifiers do not substitute for access control. Never expose this local workspace directly to the public internet.

## Container recipe (provided, not locally built)

The Dockerfile builds the frontend, installs the CAD extra, runs under a non-root user and stores data under /data. For an isolated local instance:

```text
docker build -t refit .
docker run --rm -p 127.0.0.1:8000:8000 -v refit-data:/data refit
```

The image defaults to manual object confirmation. For Gemini, supply server-side environment configuration and consent per analysis. Local Ollama remains loopback-only; a host-side Ollama service is not reachable as container loopback. Use the tested native path for local GPU inference. No external hosting was published during implementation.

Public deployment is a separate integration: add authentication, per-user access controls and quotas, request/upload limits at the reverse proxy, TLS, retention/deletion controls, and an independently tested worker strategy. Keep secrets out of frontend builds and packages.
