# <img src="logo.svg" width="40" height="20" alt=""> barebonesCRM

A CRM for one person running a few outreach campaigns. It is a folder: three JSON files,
a Python script from the standard library, one HTML page, and git as the database. Clone it,
run it, replace the sample lead with your own, and you have a working board in under a minute.

## Why it exists

Most CRMs are built for sales teams: seats, pipelines, integrations, a pricing page. If you
are one person pitching a book, a talk, a product or yourself to a few hundred people across
a handful of campaigns, that machinery costs more attention than it saves. The spreadsheet you
fall back to has the opposite problem: it holds the names but not the state. Who did I write
to, who owes me a reply, what is due today, which campaign is actually moving?

barebonesCRM answers those four questions and stops there. Every lead belongs to one campaign
and one organization, sits in one named state, and knows whose turn it is. The board shows
what is due, how each campaign is converting, and the history of every conversation. That is
the whole job.

## Built for one person

This is a single-user tool, and that is a design choice rather than a gap. Almost everything
that makes a CRM heavy exists to serve more than one user: accounts and roles, permission
checks, a hosted database, conflict handling, an admin panel, a billing model. Take the second
user away and all of it can go.

What is left is what a single operator actually gains:

- **Your data is yours, on your disk.** Three readable JSON files in a git repo. No vendor,
  no export button, no account to lose. `grep` works on it.
- **No login, ever.** The board opens on localhost and is already you. There is nothing to
  remember, expire or reset.
- **Every change is a commit.** The history of your outreach is the git log. Undo is
  `git revert`. Backup is `git push`.
- **Small enough to change.** One server script, one page, one model file. When your process
  changes, you edit the tool to match instead of working around it.
- **Nothing to keep alive.** No service to renew, no database to migrate, no dependency to
  update. If you stop using it for a year it still runs.

The same choice sets a hard ceiling: it does not scale to a second person. That is covered
under limitations below. If you work alone, that ceiling is above you.

## The lean structure

There is no database, no build step, no framework, and no dependency to install.

- **Data is three JSON files** at the repo root: `campaigns.json`, `organizations.json`,
  `leads.json`. Open them in any editor. Diff them in git. Back them up by pushing.
- **The server is one script**, `crm.py`, using Python's standard library only. It serves
  the page and accepts small delta writes. Each write is applied to fresh state and committed,
  so git history is your audit trail and your undo.
- **The page is one file**, `bbCRM.html`, in vanilla JavaScript. Three views (Today, Campaigns,
  People) plus a CSV importer and a plain-English Ask tab. Today splits into Today / Overdue /
  Future-flagged; a person card shows and edits role and LinkedIn/X/website links. No bundler.
- **The rules live in one module**, `model.py`. Entity shapes, validation, and how a
  delta is applied. If you want a new field or a new state, this is the only file
  you have to understand first.
- **Two writers can coexist** because they own different files. The UI owns the model.
  An optional bot (not included) owns observations and an unmatched-inbox file. The view
  merges them, and a human decision always wins.

You can read all of it in an afternoon, which is the point: a tool you fully understand is one
you will keep using and keep fixing.

## Limitations, on purpose

Know these before you adopt it.

- **Single user.** This is the main one, and the flip side of the section above. There
  are no accounts, no roles, no shared access, and a global lock that allows one write at a
  time. A colleague cannot log in because there is no login. Two people editing the same
  repo would fight over git. A team needs a different tool. Do not expose the port to a
  network.
- **Git is the persistence layer.** Every save runs a pull, a commit, and a push. Without a
  remote it still commits locally, but a broken git state means broken saves. Keep the repo
  clean.
- **Hundreds of leads, not hundreds of thousands.** Every request reloads the JSON from disk
  and the page holds everything in memory. It is fast at the scale it was built for and will
  not stay fast far beyond it.
- **No sync, no reminders.** Nothing reads your mail, nothing sends you a notification. The
  Today view is the reminder. Email and calendar hooks are yours to add.
- **No reporting beyond the funnel.** Per-campaign state counts and due items are what you
  get. Charts, exports and dashboards are not here.
- **The schema is opinionated.** The `facts` block on a lead reflects the outreach it was
  extracted from (paid or free, format sent, physical copy offered). Edit `model.py` to make
  it yours rather than working around it.
- **The Ask tab needs an assistant.** It uses a locally installed Claude Code (`claude`) with
  no API key, or falls back to an `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` you set. With neither,
  it stays off. Either way it sends a compact summary of your data to the model.

If those constraints fit, the rest of this file is everything you need.

## Set it up

Steps 1 to 3 need nothing but Python 3 and git. Steps 4 and 5 are optional and each touch one
external service.

**1. Fork, make it private, clone.** Fork this repo on GitHub, switch the fork to **private**
before you put a real name in it, then clone your fork. Your fork is where every save gets
pushed. If you clone this repo directly, saves still land on disk but every push fails
silently, because you cannot push here.

**2. Run it.**

```
python3 crm.py
```

Open **http://localhost:8787/bbCRM.html**. Set `CRM_PORT` to run a second copy on another port. Running via `crm.py` rather than opening the file
directly is what makes writes work: edits POST to the server, which applies the change and
commits it. Opened as a bare `file://`, the page is read-only.

**3. Replace the sample.** The repo ships one placeholder campaign, organization and lead.
Empty them before importing, since the importer adds and never replaces:

```
printf '[]' > leads.json; printf '[]' > organizations.json; printf '[]' > campaigns.json
```

Then use the **Import CSV** tab. It creates the campaign, maps your columns and de-duplicates
organizations by name. One CSV per campaign. Details under Onboarding below.

**4. Optional: the Ask tab.** If you have Claude Code installed, the Ask tab just works — it
runs the local `claude` CLI with your own logged-in session, no key. Otherwise export one API
key before starting the server. Skip it and everything else works.

```
# nothing to do if `claude` (Claude Code) is on your PATH, or:
export ANTHROPIC_API_KEY=sk-ant-...      # Claude, or
export OPENAI_API_KEY=sk-...             # ChatGPT
python3 crm.py
```

**5. Optional: the bot.** A daily process that reads your mail, matches replies to leads,
and marks them on the Today view. Not shipped here. What is shipped is the file contract it
writes to and the UI that renders it. You need leads in the CRM first, a git remote the bot
can push to, a mail source it can read, and a schedule. **[BOT.md](BOT.md)** has the contract,
the full prerequisites, and a ready-to-paste prompt for a hosted agent with a Gmail connector.

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
decided the field yourself. This repo ships without a bot. The endpoints and file split are
here so you can add one; [BOT.md](BOT.md) is the contract.

## Endpoints (`crm.py`)

- `GET /campaigns` `/organizations` `/leads` `/trail` `/observations` `/unmatched`
  `/comments` `/followups`
- `POST /lead` `/org` `/campaign` — single-field delta writes `{id, <field>}`; the server
  validates, applies onto freshly-loaded state, and commits. Unknown id → 404.
- `POST /comment` — append a dated log entry `{key, text}`.
- `POST /followup` — set/clear a follow-up date, or close/reopen an item.
- `POST /import` — create leads (and their orgs) from mapped CSV rows into a campaign,
  creating the campaign if it doesn't exist yet. Optional `dismissLinks` drops the matching
  `inbox/unmatched.json` entries in the same commit (this is how Promote works).
- `POST /dismiss` — drop `inbox/unmatched.json` entries by link without promoting.
- `POST /ask` — plain-English Q&A about your CRM via an LLM (see below).

Writes are **deltas**, never the whole store, so concurrent edits don't overwrite each other.

## Files

| File | What |
|---|---|
| `crm.py` | stdlib HTTP server + delta-write endpoints (git commit on write) |
| `model.py` | entity schema, validators, `apply_delta` |
| `app-logic.js` | pure join / roll-up / funnel / due helpers (browser + Node) |
| `bbCRM.html` | the board: Today, Campaigns, People, Import CSV, Unmatched, Ask + write-back controls |
| `campaigns/organizations/leads.json` | the data (ships with one sample of each) |
| `test_*.py`, `test_app_logic.js` | plain-assert tests (`python3 test_x.py`, `node test_app_logic.js`) |
| `BOT.md` | the contract for an optional mail-reading bot, plus a paste-ready example |

## Tests

```
python3 test_model.py
python3 test_delta.py
python3 test_endpoints.py
node test_app_logic.js
```

## Notes

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
in plain English. It reads a compact summary of your data — campaign funnels plus what needs
attention now (overdue, waiting-on-you, and bot-flagged leads) and the person you're viewing —
but is **read-only**: it explains and points you at the right control; it never changes data.

Provider order:

1. **Local Claude Code.** If the `claude` CLI is on your PATH, the Ask tab uses it with your own
   logged-in session — **no API key**. It runs `claude -p` from a temp dir (question on stdin),
   defaulting to the `sonnet` model for speed.
2. **API key.** With no CLI, export `ANTHROPIC_API_KEY` (Claude) or `OPENAI_API_KEY` (ChatGPT)
   before starting the server.

```
export ANTHROPIC_API_KEY=sk-ant-...      # only needed if you have no local `claude`
python3 crm.py
```

Override the model with `CRM_LLM_MODEL` (and the CLI path with `CRM_CLAUDE_BIN`). An API key
stays server-side, never sent to the browser. The HTTP paths use the standard library (`urllib`)
so the project keeps **zero dependencies**.

## Fork it and make it yours

This is a starting point, not a product. The logic is small and readable on purpose — clone or
fork the repo and change it to fit your workflow:

- **`model.py`** — the entity rules (fields, states, validation). Widen or tighten them here.
- **`bbCRM.html`** — the views and controls (one file, vanilla JS, no build step).
- **`crm.py`** — the endpoints (add your own; each write is a git commit).

If you're not sure how a piece works, run it and ask the **Ask** tab, or fork and experiment —
nothing here is precious.

## License

MIT — see [LICENSE](LICENSE). Use it however you like.
