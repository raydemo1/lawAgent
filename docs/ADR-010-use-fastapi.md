# ADR-010: Use FastAPI for the Local Review API

**Status:** Accepted
**Date:** 2026-07-06

## Context

Issue 10 requires exposing the review flow through a local JSON API. The original spec preferred the Python standard library (`http.server` or `wsgiref.simple_server`) to avoid new dependencies.

After evaluating the standard-library approach, we identified significant boilerplate costs:

1. **JSON parsing/validation**: `http.server` provides no built-in JSON body parsing or schema validation. Every endpoint would need manual `json.loads`, manual field checking, and manual 400/422 error formatting.
2. **Routing**: No path-based routing — each URL pattern must be matched manually in a `do_POST`/`do_GET` handler.
3. **CORS**: Must be implemented by manually setting `Access-Control-Allow-Origin` headers on every response, including `OPTIONS` preflight handling.
4. **OpenAPI docs**: No automatic schema generation — the frontend has no `/docs` endpoint to discover API contracts.
5. **Error formatting**: Unhandled exceptions produce HTML 500 pages by default; structured JSON errors require custom try/except wrapping.
6. **Testing**: Standard-library servers require starting a background thread or process for integration tests; FastAPI provides `TestClient` for synchronous in-process testing.

The codebase already uses Pydantic extensively (`StrictModel` base for all schemas), making FastAPI's Pydantic-native request/response models a natural fit.

## Decision

Adopt **FastAPI** + **uvicorn** as the web framework for the review API.

- `law_agent/review/api.py` contains the FastAPI app instance and route handlers.
- Pydantic models in `api.py` wrap the existing `ReviewCase`, `ReviewResult`, `RetrievalTrace` schemas for API serialization.
- `uvicorn` serves the app via `python -m law_agent.review serve`.
- CORS is handled by `fastapi.middleware.cors.CORSMiddleware`.

## Alternatives Considered

| Option | Pros | Cons |
|---|---|---|
| `http.server` (stdlib) | Zero dependencies | Massive boilerplate: manual JSON, routing, CORS, errors, no docs |
| Flask | Mature, simple | No native async, no automatic OpenAPI, needs `werkzeug` |
| FastAPI | Pydantic-native, OpenAPI docs, TestClient, async-ready | New dependency (fastapi + uvicorn) |

## Consequences

- **New dependencies**: `fastapi`, `uvicorn[standard]` added to `pyproject.toml`.
- **Testing**: Use `fastapi.testclient.TestClient` for synchronous unit tests without background servers.
- **Frontend dev**: `/docs` endpoint provides interactive OpenAPI docs for frontend integration.
- **Future-proofing**: FastAPI's async support allows future migration to async retrieval (e.g., real embedding API calls) without changing the framework.
