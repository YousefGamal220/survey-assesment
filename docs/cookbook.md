# Cookbook

Concrete, end-to-end walkthroughs. Each example is a copy-pasteable shell session against a locally-running stack (`docker compose up`). Every request assumes:

```bash
API=http://localhost:8000/api/v1
ACCESS=<access token from POST /auth/login>
```

Tokens are org-scoped. The `POST /auth/login` response body contains `access` and `refresh`. Re-issue `access` via `POST /auth/token` with `{"refresh": "..."}`.

---

## 1. Build a 3-section survey with a conditional section and a field dependency

**Goal:** an "Employment" survey where section 2 ("Company details") only shows if the respondent answers *Yes*, and a field inside section 2 ("Annual bonus") only shows if their role is *manager*. Section 3 is always visible.

```bash
curl -sS -X POST "$API/surveys/" \
  -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Employment survey",
    "description": "Pilot v1",
    "sections": [
      {
        "position": 0, "title": "Basics",
        "fields": [
          {"key": "employed", "position": 0, "type": "single_choice",
           "label": "Are you employed?", "required": true,
           "config": {"choices": [
             {"value": "yes", "label": "Yes"},
             {"value": "no",  "label": "No"}
           ]}}
        ]
      },
      {
        "position": 1, "title": "Company details",
        "visible_when": {"field": "employed", "op": "eq", "value": "yes"},
        "fields": [
          {"key": "company_name", "position": 0, "type": "short_text",
           "label": "Company", "required": true},
          {"key": "role", "position": 1, "type": "single_choice",
           "label": "Role", "required": true,
           "config": {"choices": [
             {"value": "ic",      "label": "Individual contributor"},
             {"value": "manager", "label": "Manager"}
           ]}},
          {"key": "annual_bonus", "position": 2, "type": "number",
           "label": "Annual bonus (USD)",
           "visible_when": {"field": "role", "op": "eq", "value": "manager"},
           "config": {"sensitive": true, "min": 0}}
        ]
      },
      {
        "position": 2, "title": "Feedback",
        "fields": [
          {"key": "comments", "position": 0, "type": "long_text",
           "label": "Anything else?"}
        ]
      }
    ]
  }'
```

**What happened.** The server persisted three `Section` rows and five `Field` rows under one new `Survey` in status `draft`. `visible_when` lives on both `Section` (section-level gate) and `Field` (field-level gate); both are evaluated by the same `apps.surveys.logic.evaluate()` pure function at submit time. `config.sensitive: true` on `annual_bonus` marks that field for per-cell Fernet encryption the moment an answer is persisted — the server never writes plaintext to disk.

Publish it:

```bash
SID=<id from the response above>
curl -X POST "$API/surveys/$SID/publish/" -H "Authorization: Bearer $ACCESS"
```

Only `draft` → `published` is allowed. Once published, edits require `POST /surveys/{id}/new_version/`, which clones the whole tree into a new row sharing `survey_group_id` and bumps `version`.

---

## 2. Submit a response, see it fail validation, fix it, succeed

**Goal:** demonstrate the validator rejects a missing required answer whose visibility resolves to *true*, and show that answers for hidden fields are silently ignored.

```bash
# Start a draft — idempotent: re-POST returns the same row
DRAFT=$(curl -sS -X POST "$API/surveys/$SID/responses/" \
  -H "Authorization: Bearer $ACCESS" -H "Content-Type: application/json" \
  -d '{}' | jq -r .id)

# Say we're employed, but forget to fill in company_name
curl -X PATCH "$API/surveys/$SID/responses/$DRAFT/" \
  -H "Authorization: Bearer $ACCESS" -H "Content-Type: application/json" \
  -d '{"answers": {"employed": "yes", "role": "ic"}}'

# Try to submit
curl -sS -X POST "$API/surveys/$SID/responses/$DRAFT/submit/" \
  -H "Authorization: Bearer $ACCESS"
```

Response (HTTP 400):

```json
{
  "error": {
    "code": "validation_error",
    "message": "Submission failed validation.",
    "details": {"company_name": ["This field is required."]}
  },
  "request_id": "..."
}
```

The evaluator walked the tree: section 2's gate (`employed == "yes"`) passed, so section 2 became visible; `company_name.required` fired; `annual_bonus.visible_when` (`role == "manager"`) resolved to *false*, so no requirement on that field.

Fix and retry:

```bash
curl -X PATCH "$API/surveys/$SID/responses/$DRAFT/" \
  -H "Authorization: Bearer $ACCESS" -H "Content-Type: application/json" \
  -d '{"answers": {"company_name": "Acme"}}'

curl -sS -X POST "$API/surveys/$SID/responses/$DRAFT/submit/" \
  -H "Authorization: Bearer $ACCESS"
```

Response: HTTP 200 with `status: "submitted"` and `submitted_at` set. The row is now immutable — further `PATCH`/`DELETE` return 409.

---

## 3. Start a response, save halfway, resume, submit

**Goal:** prove the draft survives a logout/login cycle — the respondent's UX is "close tab, come back tomorrow".

```bash
# Day 1: start and partially fill
DRAFT=$(curl -sS -X POST "$API/surveys/$SID/responses/" \
  -H "Authorization: Bearer $ACCESS" -H "Content-Type: application/json" \
  -d '{}' | jq -r .id)

curl -X PATCH "$API/surveys/$SID/responses/$DRAFT/" \
  -H "Authorization: Bearer $ACCESS" -H "Content-Type: application/json" \
  -d '{"answers": {"employed": "yes", "company_name": "Acme"}}'

# --- user closes laptop, tokens expire ---

# Day 2: log in again, list *my* drafts
curl -sS "$API/responses/mine/?status=draft" \
  -H "Authorization: Bearer $NEW_ACCESS"
```

The response contains the same `id` as `$DRAFT`. The "list mine" endpoint is the recovery hook — no cookie, no local storage, just: *show me my open drafts*.

`POST /surveys/{sid}/responses/` with an empty body would also return the same row: the endpoint is idempotent because a partial unique index on `(organization, survey, respondent) WHERE status = 'draft'` guarantees at most one active draft per person per survey. Two concurrent "start" requests cannot produce duplicates.

Finish and submit:

```bash
curl -X PATCH "$API/surveys/$SID/responses/$DRAFT/" \
  -H "Authorization: Bearer $NEW_ACCESS" -H "Content-Type: application/json" \
  -d '{"answers": {"role": "manager", "annual_bonus": 15000, "comments": "Great survey"}}'

curl -X POST "$API/surveys/$SID/responses/$DRAFT/submit/" \
  -H "Authorization: Bearer $NEW_ACCESS"
```

`annual_bonus` is stored as ciphertext in `Answer.value_encrypted`; `value_json` stays `null`.

---

## 4. Admin creates a second user, assigns "Analyst", verifies permissions

**Goal:** end-to-end RBAC: admin provisions a user, that user can list submitted responses but cannot publish a survey.

User + membership creation is currently performed via the Django admin or `manage.py shell` — there is no public `POST /auth/users/` endpoint yet (see "What's stubbed" in the README). The role hierarchy and enforcement *are* fully wired.

```bash
# In a shell, as admin:
docker compose exec web python manage.py shell <<'PY'
from apps.accounts.models import User, Membership
from apps.organizations.models import Organization

org = Organization.objects.get(slug="acme")
u = User.objects.create_user(
    username="ana", email="ana@acme.test", password="correct horse battery staple"
)
Membership.objects.create(user=u, organization=org, role="analyst")
PY
```

Ana logs in:

```bash
ANA=$(curl -sS -X POST "$API/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "ana@acme.test", "password": "correct horse battery staple", "organization_slug": "acme"}' \
  | jq -r .access)
```

What she *can* do:

```bash
curl -sS "$API/surveys/"                             -H "Authorization: Bearer $ANA"   # 200
curl -sS "$API/surveys/$SID/responses/"              -H "Authorization: Bearer $ANA"   # 200, submitted only
curl -sS "$API/audit-log/"                           -H "Authorization: Bearer $ANA"   # 200
```

What she *cannot*:

```bash
curl -sS -X POST "$API/surveys/$SID/publish/" \
  -H "Authorization: Bearer $ANA"
```

Response (HTTP 403):

```json
{
  "error": {
    "code": "permission_denied",
    "message": "Admin role required.",
    "details": {}
  },
  "request_id": "..."
}
```

`IsOrgAdmin` runs before the view body; the refusal is logged to `AuditLog` with `status_code: 403`. Ana also sees encrypted fields as the redaction token `"[encrypted]"` when retrieving a submitted response — only `admin` members see plaintext.

---

## Appendix: error envelope

Every error — DRF, Django, or custom — is shaped:

```json
{
  "error": {
    "code": "snake_case_code",
    "message": "Human-readable summary.",
    "details": { "field_name": ["..."] }
  },
  "request_id": "01JABCDEF..."
}
```

`request_id` is stamped by `RequestIdMiddleware` and flows through structured logs + the audit log, so "grep this ID across systems" is the happy-path for incident forensics.
