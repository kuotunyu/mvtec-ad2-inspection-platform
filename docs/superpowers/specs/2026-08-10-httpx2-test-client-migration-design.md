# HTTPX2 Test Client Migration Design

## Problem

Starlette 1.6 supports `httpx2` as its maintained TestClient backend and emits a
deprecation warning when it falls back to legacy `httpx`. The project declares
`httpx` as a production dependency even though repository code never imports
it; tests use FastAPI/Starlette TestClient instead. The ML extra separately
receives legacy `httpx` through anomalib/huggingface-hub.

## Decision

- Remove the unused direct production `httpx` dependency.
- Add `httpx2>=2.7,<3` to the development dependency group.
- Let Starlette prefer `httpx2` during tests while allowing the ML graph to
  retain its independent legacy `httpx` dependency.
- Freeze the dependency placement and absence of the deprecation warning in
  tests.

This is a test-infrastructure migration, not an API behavior change. No
application imports change. Verification includes warning-as-error backend and
system tests, the full suite, production wheel dependency inspection, and the
normal exact-HEAD clean-export gate.

Official basis: Starlette release notes document HTTPX2 TestClient support and
the full extra; the PyPI-verified HTTPX2 2.7.0 release is maintained by
Pydantic.
