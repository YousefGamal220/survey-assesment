# Architecture

## Data model (ERD)

Every model marked `*` inherits `TenantScopedModel` and therefore carries an `organization_id` FK that is **not drawn on every arrow below** — it exists on all starred rows and is enforced by `TenantManager` (queries without a current-org context raise, not return empty).

```
┌──────────────────┐        ┌─────────────────┐        ┌──────────────────┐
│  Organization    │ 1───*  │   Membership    │  *───1 │       User       │
│  id (uuid)       │        │   role          │        │  email  UNIQUE   │
│  slug  UNIQUE    │        │   is_active     │        │  username        │
│  is_active       │        └─────────────────┘        └──────────────────┘
└──────────────────┘                                             │
         │ 1                                                     │ 1
         │                                                       │
         │ *                                                     │ *
┌────────┴─────────┐*                                   ┌────────┴─────────┐*
│     Survey       │◄────── survey_group_id (uuid) ─────│    Response      │
│  id              │        pinned across versions      │  status          │
│  survey_group_id │                                    │  started_at      │
│  version         │                                    │  submitted_at    │
│  status          │◄──── survey_id  1:N  Response      │  survey_id  FK   │
│  published_at    │                                    │  respondent_id   │
│  created_by      │                                    └────────┬─────────┘
└────────┬─────────┘                                             │ 1
         │ 1                                                     │
         │ *                                                     │ *
┌────────┴─────────┐*                                   ┌────────┴─────────┐*
│     Section      │                                    │     Answer       │
│  position        │                                    │  field_key       │
│  title           │                                    │  value_json      │
│  visible_when    │ (JSON DSL)                         │  value_encrypted │ (Fernet)
└────────┬─────────┘                                    └──────────────────┘
         │ 1                                                     ▲
         │ *                                                     │
┌────────┴─────────┐*                                            │ referenced by
│      Field       │───────── field.key string ──────────────────┘ field_key (not FK — survives versioning)
│  key             │
│  type            │ (name → FieldType registry)
│  required        │
│  config          │ (JSON, includes `sensitive: true` for encryption)
│  visible_when    │ (JSON DSL)
└──────────────────┘

┌──────────────────┐
│    AuditLog      │   BigAutoField id, not tenant-scoped model but
│  organization FK │   always carries organization FK explicitly.
│  user_email      │   User FK is SET_NULL — email preserved on user delete.
│  method, path    │
│  status_code     │
│  request_id      │
│  extra (JSON)    │
│  created_at  idx │
└──────────────────┘
```

**Why `Answer.field_key` is a string, not a FK.** Publishing a survey forks a new version but leaves existing responses pinned to the version they started in. A FK to `Field` would dangle the moment an admin deletes a field from a future draft. A string key is the cheapest correct choice: schemas are immutable-on-publish, keys are unique within a version, and the field's metadata at submit time is all the evaluator needs.

Regenerate a richer version any time with:

```bash
poetry run python manage.py graph_models accounts organizations surveys responses audit \
  --pydot -o docs/erd.png
```

(`django-extensions` is already installed; the diagram above is the hand-drawn "read it without a renderer" version.)

---

## Request flow: submitting a response

```
Client
  │  POST /api/v1/surveys/{sid}/responses/{id}/submit/
  ▼
RequestIdMiddleware                                       [stamps X-Request-ID into contextvars]
  ▼
CurrentOrgMiddleware                                      [resolves org from access token claims;
  ▼                                                         sets contextvar consumed by TenantManager]
JWTAuthentication  ──► sets request.user
  ▼
DRF Router ──► ResponseViewSet.submit()                   [permission: IsOwnerOrOrgAdmin]
  ▼
submit_response(response)  in apps.responses.services
  │
  ├─ load survey tree with select_related/prefetch_related
  │
  ├─ build visibility map:
  │    for each Section, Field:
  │      visible = logic.evaluate(node.visible_when, answers_by_key)
  │
  ├─ validate:
  │    for each visible Field:
  │      - required?         → field_validators.required(answer)
  │      - field type rules? → FieldType.validate(answer, config)
  │    accumulate errors into a dict
  │
  ├─ if errors: raise ValidationError
  │    ▼
  │    exception handler wraps it into {error: {...}, request_id}
  │    ▼
  │    AuditMiddleware (response phase) writes 400 + user + path to AuditLog
  │
  ├─ else:  (inside transaction.atomic)
  │    - persist/update Answer rows
  │        sensitive fields: Fernet-encrypt into value_encrypted, null value_json
  │    - set response.status = "submitted", response.submitted_at = now()
  │    - save
  │
  ▼
SurveyCache.invalidate(survey_id) is NOT called here — submission doesn't
change the survey tree. The survey-detail cache is only invalidated by
post_save/post_delete signals on Survey/Section/Field.
  ▼
AuditMiddleware writes 200 row.
  ▼
Structured-JSON log line with request_id, user, org, duration_ms.
  ▼
Response body: serialized Response with nested answers
                 (encrypted cells redacted based on caller's role).
```

---

## Caching strategy

| Cache                         | Backend        | TTL   | Invalidation                                                                                  |
|-------------------------------|----------------|-------|------------------------------------------------------------------------------------------------|
| Survey detail JSON            | Redis (django-redis) | 60 s  | `post_save`/`post_delete` signals on `Survey`, `Section`, `Field` → `SurveyCache.invalidate(survey_id)` |
| Survey list *per-tenant*      | Not cached     | —     | Short-lived + cheap index scan; cost of stale list > benefit                                   |
| Rate-limit counters           | Redis          | 1 min | Self-expiring (TTL = window)                                                                  |
| JWT blacklist (logout)        | Redis          | token lifetime | TTL matches refresh-token expiry                                                          |

Design rules:

- **Only cache the GETs that dominate the hot path.** Respondents landing on a published survey hit `/surveys/{id}/` repeatedly; analysts hit list endpoints rarely.
- **Never cache lists keyed solely by path.** They leak across tenants. When introducing new caches, the key must include `organization_id` or be written through `CurrentOrgMiddleware`-aware helpers.
- **Invalidate on write, not on read.** Signal handlers live in `apps.surveys.signals`; adding a new tree-shaped model means registering it there too.
- **TTL is a safety net, not the primary correctness mechanism.** If signals broke, a stale read would self-heal within 60 s.

---

## Scaling notes

### Where state lives

| Component          | State?         | Scales how                                  |
|--------------------|----------------|---------------------------------------------|
| Django web (gunicorn + uvicorn worker) | Stateless — JWT in `Authorization` header | Add pods behind the LB |
| Postgres           | Source of truth | Vertical first; read replicas next          |
| Redis              | Cache + Celery broker + rate-limit counters | Managed Redis cluster; cache and broker can be separate instances once both grow |
| Celery workers     | Stateless      | Add pods; partition queues by workload      |

### Deploying with N replicas

1. **Terminate TLS at Traefik** (already configured in `docker-compose.prod.yml`). The web pods serve plain HTTP inside the cluster.
2. **Shared secret + JWT key.** Every web pod must use the same `SECRET_KEY` and `JWT_SIGNING_KEY`. A pod with different keys will silently reject tokens minted by its siblings.
3. **Migrations.** Run `manage.py migrate` from **one** pod (init container or one-shot job) before rolling out web pods. Application-level code must be forward-compatible with the *previous* schema during the rollout window.
4. **Cache warm-up is not needed.** 60 s TTL + on-demand population means cold pods work immediately.
5. **Sticky sessions not required.** JWT is bearer-token; any pod can handle any request.

### Bottlenecks at scale

- **Submit path.** Transactional `submit_response` writes one `Response` update + N `Answer` rows. Under load, row contention is on the response row itself (single-row update — fine) rather than the survey tree (read-only).
- **Audit log writes.** Every authenticated request inserts one `AuditLog` row. This is the first thing to move async (batched insert via Celery) if write IOPS becomes the ceiling. The `organization, -created_at` composite index makes reads cheap, but it means writes maintain an index whose last page is always hot.
- **CSV export.** Already async. The risk is a single export task fetching a million-row `Answer` table into memory — production should chunk by PK range or `.iterator(chunk_size=5000)`.
- **JSON `visible_when` evaluation.** Pure-Python, fast for the survey sizes we expect (< 500 fields), but the evaluator is O(fields × rules). If survey size explodes, hoist evaluation into a single tree walk with a memoized `answers` dict — already the shape of the code, just needs benchmarking.
- **Rate limiting is per-pod unless backed by Redis.** `django-ratelimit` is configured with the Redis backend, so limits are cluster-wide — verify this doesn't regress when introducing a new ratelimit decorator.
