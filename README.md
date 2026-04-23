# Advanced Dynamic Survey Platform

Enterprise backend for designing, deploying, and analyzing dynamic surveys with conditional logic, cross-section dependencies, versioning, encrypted sensitive fields, partial-save resume, RBAC, audit trails, and async reporting. Django 6 + DRF, Postgres, Redis, Celery, JWT.

---

## Contents

- [Quickstart](#quickstart)
- [Auth flow](#auth-flow)
- [Endpoint reference + usage examples](#endpoint-reference--usage-examples)
- [Architecture](#architecture)
- [Testing & QA](#testing--qa)
- [API versioning](#api-versioning)
- [Scalability & performance](#scalability--performance)
- [Security](#security)

---

## Quickstart

```bash
cp .env.example .env
docker compose up --build
```

- API base:       `http://localhost:8000/api/v1/`
- Swagger UI:     `http://localhost:8000/api/docs/`
- ReDoc:          `http://localhost:8000/api/redoc/`
- OpenAPI schema: `http://localhost:8000/api/schema/`
- Django admin:   `http://localhost:8000/admin/`

Entrypoint auto-runs migrations + seeds the RBAC groups. Create a superuser:

```bash
docker compose exec web python manage.py createsuperuser
```

### Development without Docker

```bash
poetry install --with dev
cp .env.example .env                              # point DATABASE_URL / REDIS_URL locally
poetry run python manage.py migrate
poetry run python manage.py seed_rbac
poetry run python manage.py runserver
poetry run celery -A config worker -l info       # in another shell, for async tasks
```

---

## Auth flow

Two-step, org-scoped:

1. **Login** returns a refresh token + the caller's memberships.
   ```bash
   curl -sS -X POST http://localhost:8000/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"alice@acme.test","password":"…"}'
   ```
   ```json
   {
     "refresh": "eyJ…",
     "memberships": [
       {"id": 1, "org_id": "…", "org_name": "Acme", "role": "admin"}
     ]
   }
   ```

2. **Exchange** refresh + chosen org → short-lived **access token with `org_id` + `role` claims**.
   ```bash
   curl -sS -X POST http://localhost:8000/api/v1/auth/token \
     -H "Content-Type: application/json" \
     -d '{"refresh":"…","organization_id":"…"}'
   # → {"access":"eyJ…"}
   ```

3. **Use** the access token on every request:
   ```bash
   curl -sS http://localhost:8000/api/v1/surveys/ \
     -H "Authorization: Bearer $ACCESS"
   ```

4. **Switch orgs** — call `/auth/token` again with a different `organization_id`.
5. **Logout**:
   ```bash
   curl -sS -X POST http://localhost:8000/api/v1/auth/logout \
     -H "Content-Type: application/json" \
     -d '{"refresh":"…"}'
   ```

Rate limits: `/auth/login` is capped at **10 attempts / minute / IP** → 429. `/auth/token` at 30 / minute.

---

## Endpoint reference + usage examples

All examples assume `ACCESS=<your bearer token>` in the environment.

### Surveys — `/api/v1/surveys/`

| Method | Path | Role | Purpose |
| --- | --- | --- | --- |
| `GET` | `/surveys/?status=draft\|published\|archived` | analyst+ | List surveys (optionally filtered) |
| `GET` | `/surveys/latest/` | analyst+ | Latest version per survey group |
| `GET` | `/surveys/{id}/` | analyst+ | Retrieve with nested sections + fields |
| `POST` | `/surveys/` | admin | Create a draft (body = nested tree) |
| `PATCH` | `/surveys/{id}/` | admin | Edit a draft — entire tree is rewritten |
| `DELETE` | `/surveys/{id}/` | admin | Soft-archive |
| `POST` | `/surveys/{id}/publish/` | admin | Draft → published (sets `published_at`) |
| `POST` | `/surveys/{id}/new_version/` | admin | Clone a published survey → new draft (`version = N+1`, same `survey_group_id`) |

**Create a survey with cross-section conditional logic:**

```bash
curl -sS -X POST http://localhost:8000/api/v1/surveys/ \
  -H "Authorization: Bearer $ACCESS" -H "Content-Type: application/json" \
  -d '{
    "title": "Employment survey",
    "description": "Pilot v1",
    "sections": [
      {"position": 0, "title": "Basics",
       "fields": [
         {"key": "employed", "position": 0, "type": "single_choice",
          "label": "Are you employed?", "required": true,
          "config": {"choices": [
            {"value": "yes", "label": "Yes"},
            {"value": "no", "label": "No"}
          ]}}
       ]},
      {"position": 1, "title": "Company details",
       "visible_when": {"field": "employed", "op": "eq", "value": "yes"},
       "fields": [
         {"key": "company_name", "position": 0, "type": "short_text",
          "label": "Company", "required": true},
         {"key": "annual_income", "position": 1, "type": "number",
          "label": "Annual income (USD)",
          "config": {"sensitive": true, "min": 0}}
       ]}
    ]
  }'
```

The `sensitive: true` flag on `annual_income` triggers per-cell encryption at submit time. The second section's `visible_when` makes it appear only when `employed == "yes"` — a cross-section dependency evaluated both on the frontend (preview) and the backend (submit validation).

**Publish + fork a new version:**

```bash
curl -X POST http://localhost:8000/api/v1/surveys/$ID/publish/ \
  -H "Authorization: Bearer $ACCESS"

curl -X POST http://localhost:8000/api/v1/surveys/$ID/new_version/ \
  -H "Authorization: Bearer $ACCESS"
```

### Responses — submission with partial save

| Method | Path | Role | Purpose |
| --- | --- | --- | --- |
| `POST` | `/surveys/{sid}/responses/` | any member | Create (or return existing) draft — idempotent |
| `PATCH` | `/surveys/{sid}/responses/{id}/` | owner | Merge `{answers: {key: value, ...}}` into the draft |
| `POST` | `/surveys/{sid}/responses/{id}/submit/` | owner | Validate + lock (full `visible_when`-gated `required` + per-type validators) |
| `GET` | `/surveys/{sid}/responses/{id}/` | owner or analyst+ | Retrieve (analysts only see submitted) |
| `DELETE` | `/surveys/{sid}/responses/{id}/` | owner | Delete draft (submitted responses are immutable) |
| `GET` | `/surveys/{sid}/responses/` | analyst+ | List submitted (tenant-scoped) |
| `GET` | `/responses/mine/` | any member | Caller's own responses across all surveys |

**Full submission walkthrough:**

```bash
# 1. Start (or resume) a draft — idempotent: re-POST returns the same row
DRAFT=$(curl -sS -X POST http://localhost:8000/api/v1/surveys/$SID/responses/ \
  -H "Authorization: Bearer $ACCESS" -H "Content-Type: application/json" \
  -d '{}' | jq -r .id)

# 2. Save answers in increments — as many PATCH calls as you like
curl -X PATCH http://localhost:8000/api/v1/surveys/$SID/responses/$DRAFT/ \
  -H "Authorization: Bearer $ACCESS" -H "Content-Type: application/json" \
  -d '{"answers": {"employed": "yes"}}'

curl -X PATCH http://localhost:8000/api/v1/surveys/$SID/responses/$DRAFT/ \
  -H "Authorization: Bearer $ACCESS" -H "Content-Type: application/json" \
  -d '{"answers": {"company_name": "Acme", "annual_income": 120000}}'

# 3. Submit — validates visible_when + required + per-type constraints, locks the row
curl -X POST http://localhost:8000/api/v1/surveys/$SID/responses/$DRAFT/submit/ \
  -H "Authorization: Bearer $ACCESS"
```

**Encryption visibility:** `annual_income` is stored as ciphertext in `Answer.value_encrypted`. Admins retrieve plaintext; analysts see `"[encrypted]"`. The CSV export task redacts encrypted cells.

### Audit log — `/api/v1/audit-log/`

Append-only request log. Analyst+ can list rows for their own org.

```bash
curl -sS "http://localhost:8000/api/v1/audit-log/?method=POST&path_contains=publish" \
  -H "Authorization: Bearer $ACCESS"
```

### Async tasks (Celery)

Run a worker:
```bash
poetry run celery -A config worker -l info
```

Kick off from a Django shell or signal:
```python
from apps.responses.tasks import export_survey_csv, aggregate_response_counts
csv_string = export_survey_csv.delay(str(survey_id)).get()
counts = aggregate_response_counts.delay(str(survey_id)).get()  # {draft: N, submitted: N}
```

---

## Architecture

```
apps/
├── core/            # TimestampedModel, TenantScopedModel, permissions, RequestIdMiddleware, exception envelope
├── organizations/   # Organization (tenant) + CurrentOrgMiddleware
├── accounts/        # User (email login), Membership, JWT auth, rate-limited login/token
├── surveys/         # Survey/Section/Field + field-type registry + visible_when DSL engine
├── responses/       # Response/Answer + submit service + per-cell encryption + Celery tasks + cache
└── audit/           # AuditLog + middleware capturing every authenticated request
config/
├── settings/        # base / dev / prod / test
├── urls.py          # /api/v1/ namespace + spectacular docs
└── celery.py        # Celery app singleton
locustfile.py        # Load-test harness
```

### Highlights

- **Row-level multi-tenancy.** Every tenant-owned model inherits `TenantScopedModel`. `TenantManager` filters every query by a `contextvars`-backed current-org context and **raises** if no tenant is set — cross-tenant leaks fail loudly.
- **Org-scoped access tokens.** Refresh tokens are user-scoped; access tokens are always org-scoped.
- **RBAC.** `admin > analyst > viewer`. Permission classes `IsOrgAdmin` / `IsOrgAnalyst` / `IsOrgViewer` all test "role at least X".
- **Dynamic survey builder.** JSONB `config` per field + a name-keyed `FieldType` registry. Adding a type = one class + one registry entry, zero migrations.
- **Conditional-logic DSL.** `{all|any|not}` combiners + 11 ops (`eq`, `neq`, `in`, `not_in`, `gt/gte/lt/lte`, `contains`, `is_set`, `is_not_set`) — pure Python, pure-function `evaluate(rule, answers) -> bool`. Cross-section dependencies work for free because rules reference fields by `key`.
- **Versioning.** Publishing freezes a survey; new edits fork a new row (`version = N+1`, same `survey_group_id`). Existing responses stay pinned to the exact schema they saw.
- **Sensitive-field encryption.** Opt-in `sensitive: true` flag on `Field.config`. Submit time uses Fernet-backed per-cell encryption; analysts see a redaction token, admins see plaintext.
- **Draft resume.** Partial responses auto-save via `PATCH`; a respondent can close their tab and continue later. One active draft per `(org, survey, respondent)` enforced by a partial unique index.
- **Audit log.** Middleware captures method + path + status + user + org + request-id for every authenticated request (plus failed `/auth/login` attempts). Analyst+ can browse.
- **Caching + async.** 60-second Redis cache on survey detail reads, auto-invalidated via `post_save`/`post_delete` signals on Survey/Section/Field. Celery tasks for CSV export, response counts, per-field histograms, and bulk invitations.
- **Structured error envelope.** Every DRF exception maps to `{"error": {"code", "message", "details"}, "request_id": "..."}`.
- **Structured JSON logging.** `apps.core.logging.JsonRequestFormatter` injects `request_id` from contextvars.

---

## Testing & QA

```bash
poetry run pytest                       # full suite
poetry run pytest apps/responses -v     # one app
poetry run pytest -k test_submit        # by keyword
poetry run pytest --cov=apps            # coverage report
```

Currently: **163 tests · 93%+ coverage** across six apps, all green.

### Security scanning

```bash
poetry run bandit -c pyproject.toml -r apps/      # static security linter
poetry run pip-audit                               # known CVE scan
```

Both clean. CI runs them on every push.

### Load testing (PDF bucket 5)

```bash
# Seed a demo respondent + published survey, then:
SURVEY_EMAIL=demo@x.com SURVEY_PASSWORD=... SURVEY_ID=<uuid> \
  poetry run locust --users 200 --spawn-rate 20 -H http://localhost:8000 --headless -t 60s
```

`locustfile.py` mixes 80% respondent traffic (login → draft → patch × 2 → submit) with 20% analyst traffic (list surveys / list responses / audit log).

---

## API versioning

- URL-path versioning: `/api/v1/`. `v2` can coexist under `/api/v2/` with no breakage.
- OpenAPI schema auto-generated by `drf-spectacular` at `/api/schema/`.
- Swagger UI at `/api/docs/`; ReDoc at `/api/redoc/`.
- Every breaking change should spawn a new namespace; shared components are plain Python modules referenced by both versions.

---

## Scalability & performance

- **Horizontal scaling.** The web tier is stateless JWT auth — add web pods, share the Postgres + Redis backends.
- **Caching.** Survey detail reads cached for 60s; invalidated on every Survey/Section/Field write. Serving `/surveys/{id}/` from Redis means a respondent landing page never touches Postgres on repeat hits.
- **Async processing.** Celery + Redis broker. Heavy work — CSV exports, bulk invitations, aggregation — runs off the request path.
- **Indexed hot paths.** `Response(organization, survey, status)`, `Answer(organization, field_key)`, `AuditLog(organization, -created_at)` composite indexes match the most common list queries.
- **Prefetch discipline.** List endpoints use `select_related` for FK parents and `prefetch_related` for reverse collections to collapse N+1 queries into two round-trips.
- **Partial unique constraints.** One active draft per `(org, survey, respondent)` enforced by a Postgres partial unique index — cheaper than application-level dedup and race-free.

---

## Security

- JWT with short-lived (15 min) org-scoped access tokens and longer refresh tokens (7 days, rotatable + blacklistable).
- `django-ratelimit` on auth endpoints to block credential stuffing.
- Per-cell encryption via Fernet (symmetric AES-128-CBC + HMAC) keyed on `FIELD_ENCRYPTION_KEY`.
- `bandit` + `pip-audit` in CI.
- Django's built-in SQL parameterization + ORM protects against injection; DRF's JSON-only default + CSRF-exempt bearer-auth flow plus output escaping in Swagger UI protect against XSS.
- Audit log persists every request, including failed login attempts, for forensics.
- Role-based permissions + object-level checks on responses (owner-only for draft mutations).
