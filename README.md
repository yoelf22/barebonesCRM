# barebonesCRM

A tiny, file-based CRM you can run from one folder. No database, no build step, no
framework — just Python's standard library, a static HTML page, and git as the datastore.

It models outreach as **Campaigns → Organizations → Leads**, with a lightweight per-lead
**comms trail**, and serves three views (Today, Campaigns, People) from a thin-client page.

## Run it

```
python3 crm.py
```

Then open **http://localhost:8787/app.html**.

Running via `crm.py` (rather than opening the file directly) is what makes **writes** work:
edits POST to the server, which applies the change and `git commit`s it. Opened as a bare
`file://`, the page is read-only.

## The model

Four entities, stored as normalized JSON at the repo root:

- **`campaigns.json`** — a marketing motion. Each campaign has `targetType`
  (`individual` | `organization`), a `goal`, and its own ordered `states`, each tagged
  `kind: active | won | lost`.
- **`organizations.json`** — department-grained orgs. An org's status is *derived* from its
  leads (alive = has a non-lost lead), never stored.
- **`leads.json`** — the people. Each lead belongs to one org and one campaign, carries
  contact details, a `state` (from its campaign), `followUpDate`, `waiting` (`me` | `them`),
  and structured `facts`.
- **comms** — `comments.json` (a dated per-lead log) and `trail.json` (optional event feed).

### Ownership split (human vs. automation)

Two writers can share the data without clobbering each other because they own different files:

- **Human / UI-owned** (edited through the page): `campaigns.json`, `organizations.json`,
  `leads.json`, `followups.json`.
- **Bot-owned** (append-only, for an optional sync agent): `observations.json`,
  `comments.json`, `inbox/unmatched.json`.

The UI merges them **human-over-bot**: an automated suggestion shows only where you haven't
decided the field yourself. (This repo ships without a bot; the endpoints and file split are
here so you can add one.)

## Endpoints (`crm.py`)

- `GET /campaigns` `/organizations` `/leads` `/trail` `/observations` `/unmatched`
  `/comments` `/followups`
- `POST /lead` `/org` `/campaign` — single-field delta writes `{id, <field>}`; the server
  validates, applies onto freshly-loaded state, and commits. Unknown id → 404.
- `POST /comment` — append a dated log entry `{key, text}`.
- `POST /followup` — set/clear a follow-up date, or close/reopen an item.

Writes are **deltas**, never the whole store, so concurrent edits don't overwrite each other.

## Files

| File | What |
|---|---|
| `crm.py` | stdlib HTTP server + delta-write endpoints (git commit on write) |
| `model.py` | entity schema, validators, `apply_delta` |
| `app-logic.js` | pure join / roll-up / funnel / due helpers (browser + Node) |
| `app.html` | the board: Today, Campaigns, People views + write-back controls |
| `campaigns/organizations/leads.json` | the data (ships with one sample of each) |
| `test_*.py`, `test_app_logic.js` | plain-assert tests (`python3 test_x.py`, `node test_app_logic.js`) |

## Tests

```
python3 test_model.py
python3 test_delta.py
python3 test_endpoints.py
node test_app_logic.js
```

## Notes

- The sample `campaigns/organizations/leads.json` contain one placeholder each — replace them
  with your own.
- If you want git-backed persistence, run `crm.py` inside a git repo with a remote; each write
  commits (and can push). Without a remote it still commits locally.

MIT-licensed; use it however you like.
