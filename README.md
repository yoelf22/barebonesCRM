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
- `POST /import` — create leads (and their orgs) from mapped CSV rows into a campaign,
  creating the campaign if it doesn't exist yet.
- `POST /ask` — plain-English Q&A about your CRM via an LLM (see below).

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

## Onboarding: import a CSV

New here? The fastest start is the **Import CSV** tab:

1. Pick an existing campaign, or choose **➕ New campaign…** and name it (it's created with
   default states: prospect → contacted → replied → won / lost).
2. Choose a `.csv` file. It's parsed **in your browser** (quoted commas handled).
3. Map columns → fields (**Name** required; Email, Organization, Role, Notes optional), pick an
   initial state, and Import. Organizations are auto-created and de-duplicated by name.

Works for any kind of list — press contacts, investors, academics, event invitees — one CSV per
campaign.

## Ask (plain-English assistant)

The **Ask** tab lets you talk to Claude or ChatGPT about how the CRM works and what to do next,
in plain English — handy while you're still learning the logic. It reads a compact summary of your
data (and the person you're viewing) but is **read-only**: it explains and points you at the right
control; it never changes data.

Enable it by exporting an API key before starting the server:

```
export ANTHROPIC_API_KEY=sk-ant-...      # uses Claude (default model: claude-opus-5)
# or
export OPENAI_API_KEY=sk-...             # uses ChatGPT (default model: gpt-4o)
python3 crm.py
```

Override the model with `CRM_LLM_MODEL`. With no key set, the Ask tab explains how to enable it.
The key stays on your machine (server-side, in the env) — it's never sent to the browser, and the
LLM call goes straight from your machine to the provider. Implemented with the standard library
(`urllib`) so the project keeps **zero dependencies**.

## Fork it and make it yours

This is a starting point, not a product. The logic is small and readable on purpose — clone or
fork the repo and change it to fit your workflow:

- **`model.py`** — the entity rules (fields, states, validation). Widen or tighten them here.
- **`app.html`** — the views and controls (one file, vanilla JS, no build step).
- **`crm.py`** — the endpoints (add your own; each write is a git commit).

If you're not sure how a piece works, run it and ask the **Ask** tab, or fork and experiment —
nothing here is precious.

## License

MIT — see [LICENSE](LICENSE). Use it however you like.
