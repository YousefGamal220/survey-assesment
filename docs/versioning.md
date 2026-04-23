# API versioning & deprecation policy

## URL scheme

All endpoints live under a version prefix:

```
/api/v1/...
```

The prefix is wired in `config/urls.py` — a list of `v1_patterns` is mounted under `path("api/v1/", include((v1_patterns, "v1")))`. Bringing up `v2` is a matter of defining `v2_patterns` and mounting them at `path("api/v2/", include((v2_patterns, "v2")))`; the two versions coexist without touching each other's code paths.

OpenAPI docs (`/api/schema/`, `/api/docs/`, `/api/redoc/`) are **intentionally unversioned** — the schema describes every mounted version in one document so clients can diff v1 against v2 without hitting two endpoints. If you prefer strict per-version schemas, split the spectacular view into `SpectacularAPIView(urlconf="config.urls_v1")` instances.

## Semantic versioning of the API

A major bump (v1 → v2) is required for any of:

- Removing an endpoint, response field, or request parameter.
- Renaming an endpoint, field, or parameter.
- Changing the type, format, or semantics of an existing field (e.g. `string` → `uuid`, `seconds` → `milliseconds`).
- Tightening validation in a way that would reject previously-accepted payloads.
- Changing the shape of the error envelope.
- Changing auth requirements or role hierarchy on an existing endpoint.

A minor change is additive and does **not** require a new version:

- Adding a new endpoint.
- Adding an optional request field with a safe default.
- Adding a new field to a response payload (clients must tolerate unknown fields).
- Adding a new value to an enum *when the enum is consumed in responses only* — if clients send it, it's breaking.
- Loosening validation.

A patch is a pure bug fix: the documented contract was wrong, and the implementation now matches the docs.

## Deprecation window

- A version is supported for **12 months** after the release of its successor.
- Deprecated endpoints respond with a `Deprecation: true` header and a `Sunset: <RFC 8594 date>` header on every response.
- The deprecation date, sunset date, and the migration target are listed in this document's "Currently deprecated" table (currently empty — v1 is the only version).
- 90 days before sunset, deprecated endpoints begin returning a `Warning: 299 - "Deprecated, sunset YYYY-MM-DD, migrate to /api/vN/..."` header.
- At sunset, the URL prefix returns HTTP 410 Gone with the error envelope:
  ```json
  {
    "error": {
      "code": "version_sunset",
      "message": "/api/v1 was retired on 2027-05-01. Migrate to /api/v2.",
      "details": {"migration_guide": "https://…/docs/migration-v1-to-v2.md"}
    },
    "request_id": "..."
  }
  ```

Sunset responses are preferred over silent 404s so clients that missed every prior signal still get a diagnostic message in logs.

## Currently deprecated

| Version | Deprecated on | Sunset on | Migration guide |
|---------|---------------|-----------|-----------------|
| *none*  | —             | —         | —               |

v1 is the only live version. Once v2 ships, add a row here and a `docs/migration-v1-to-v2.md` alongside.

## Migration guide template

When v2 ships, create `docs/migration-v1-to-v2.md` with these sections:

1. **Summary of breaking changes.** One bullet per break — what changed and why.
2. **Endpoint diff.** Table: `v1 endpoint` → `v2 endpoint` → `change type` (removed / renamed / payload-shape / semantics).
3. **Payload diff per endpoint.** Side-by-side v1/v2 JSON samples for every changed body and response.
4. **Client upgrade checklist.** Ordered list a client dev can execute top-to-bottom without rereading the spec.
5. **Backfill / data migration notes.** If persisted state changes shape (e.g. a `Field.config` key is renamed), document the one-way migration that runs server-side.
6. **Rollback plan.** Because both versions run side-by-side, rollback is "stop issuing v2 tokens" rather than "redeploy v1" — call that out explicitly.

## Internal conventions

- **Shared code** (models, services, validators, permissions) lives in `apps/<name>/` and is imported by any version. Versioning happens at the serializer and view layer, not the domain layer.
- **Per-version modules** are named with a suffix — `apps/surveys/serializers_v2.py`, `apps/surveys/views_v2.py`, `apps/surveys/urls_v2.py`. Do not branch on version inside a single file with `if request.version == "v2"` — it produces code that nobody dares to change.
- **Tests** for each version live under `apps/<name>/tests/v1/` and `apps/<name>/tests/v2/`. Parametrising the same test across versions hides regressions: one version passing masks the other failing.
- **Fixtures and factories** are shared; serialization is not.
