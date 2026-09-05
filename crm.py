#!/usr/bin/env python3
"""
Barebones CRM server.

Serves the board at http://localhost:8787/app.html and persists every edit to the
JSON files in this folder, committing each write to git.

Reads:
  GET /campaigns /organizations /leads /followups /comments
      /trail /observations /unmatched          -> the matching JSON file

Writes (each one: pull -> apply -> commit -> push, serialized by a global lock):
  POST /lead /org /campaign {id, <field>}      -> single-field delta, validated by model.py
  POST /comment  {key, text[, author]}         -> append a dated log entry
  POST /followup {key, followUpDate}           -> set/clear a follow-up date
                 {key, closed: true}           -> close the item (off the board)
                 {key, reopen: true}           -> undo a close
  POST /import   {campaignId, rows[, campaignName, defaultState, dismissLinks]}
                                               -> create leads (+ orgs, + campaign if new) from CSV rows;
                                                  dismissLinks drops promoted inbox/unmatched entries
  POST /dismiss  {links}                       -> drop inbox/unmatched entries without promoting
  POST /ask      {question, history, leadId}   -> read-only LLM answer; needs ANTHROPIC_API_KEY
                                                  or OPENAI_API_KEY in the env

Single user, localhost only, no auth. Without a git remote, writes still commit locally.

Run:  python3 crm.py     (Ctrl-C to stop; CRM_PORT=8791 to use another port)
"""
import http.server, json, os, subprocess, threading, time
from urllib.parse import urlparse
import model

ROOT = os.path.dirname(os.path.abspath(__file__))
COMMENTS = os.path.join(ROOT, "comments.json")
FOLLOWUPS = os.path.join(ROOT, "followups.json")
PORT = int(os.environ.get("CRM_PORT", 8787))   # override to run a second copy side by side
LOCK = threading.Lock()


def load():
    try:
        with open(COMMENTS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def load_followups():
    try:
        with open(FOLLOWUPS, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def load_json_file(name, default):
    try:
        with open(os.path.join(ROOT, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True)


def persist(comment):
    """Append one comment, commit comments.json only, and push. Bot-safe."""
    with LOCK:
        git("pull", "--no-edit", "--no-rebase", "-q")      # absorb overnight bot commits
        data = load()
        data.append(comment)
        with open(COMMENTS, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        git("add", "comments.json")                        # comments.json ONLY, never index.html
        git("-c", "user.name=Barebones CRM", "-c", "user.email=crm@localhost",
            "commit", "-q", "-m", "comment: " + comment["key"])
        if git("push", "-q", "origin", "main").returncode != 0:
            git("pull", "--no-edit", "--no-rebase", "-q")
            git("push", "-q", "origin", "main")
        return data


def persist_followup(key, followUpDate, author, via, closed=False, reopen=False):
    """Set or clear one human-chosen follow-up date, or close the item outright.

    `closed` is the third state: not "due later", but "done, off the board". It lives
    in the same file for the same reason a chosen date does — index.html is rewritten
    by the overnight bot every morning, so a decision stored there would not survive.

    Why a separate file rather than editing index.html's snapshot: the overnight
    digest bot rewrites st/fu inside index.html every morning. Two writers on one
    file is how you lose a decision silently. This file is written only from here,
    read by the page, and the page lets it win over the snapshot — so a date YOU
    chose survives the bot, and the bot never has to know it exists.
    """
    with LOCK:
        git("pull", "--no-edit", "--no-rebase", "-q")      # absorb overnight bot commits
        data = load_followups()
        previous = data.get(key) or {}
        if closed:
            entry = {"closed": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                     "closedBy": author, "setVia": via}
            # A date chosen by hand rides along inside the closed entry, so reopening
            # gives it back. Closing something must not silently eat the decision that
            # put a date on it in the first place.
            for carried in ("followUpDate", "setBy", "setAt"):
                if previous.get(carried):
                    entry[carried] = previous[carried]
            data[key] = entry
            message = "closed: %s" % key
        elif reopen:
            if previous.get("followUpDate"):
                # Give back exactly what closing took, including who chose the date and
                # when — a reopen that relabels the user's decision as the reopener's is a
                # quiet rewrite of the record.
                data[key] = {"followUpDate": previous["followUpDate"],
                             "setBy": previous.get("setBy", author),
                             "setVia": previous.get("setVia", via),
                             "setAt": previous.get("setAt", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))}
            else:
                data.pop(key, None)
            message = "reopened: %s" % key
        elif followUpDate:
            data[key] = {"followUpDate": followUpDate, "setBy": author, "setVia": via,
                         "setAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            message = "follow-up: %s -> %s" % (key, followUpDate)
        else:
            data.pop(key, None)
            message = "follow-up: %s cleared" % key
        with open(FOLLOWUPS, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False, sort_keys=True)
        git("add", "followups.json")                       # followups.json ONLY, never index.html
        git("-c", "user.name=Barebones CRM", "-c", "user.email=crm@localhost",
            "commit", "-q", "-m", message)
        if git("push", "-q", "origin", "main").returncode != 0:
            git("pull", "--no-edit", "--no-rebase", "-q")
            git("push", "-q", "origin", "main")
        return data


ENTITY = {
  "/lead":     ("leads.json",         {"state","followUpDate","waiting","notes",
                                        "facts","strength","emails","handles","role"}),
  "/org":      ("organizations.json", {"name","sector","region","url","campaignId"}),
  "/campaign": ("campaigns.json",     {"name","icp","goal","states","window",
                                        "targetType","notes"}),
}


def _delta_text(delta):
    """One Log line for a human lead edit: 'state → passed', 'follow-up → 2026-09-15'."""
    names = {"state": "state", "followUpDate": "follow-up", "waiting": "waiting"}
    parts = []
    for k, v in delta.items():
        if k == "id":
            continue
        if k in names:
            parts.append("%s cleared" % names[k] if v in (None, "") else "%s → %s" % (names[k], v))
        else:
            parts.append("%s updated" % k)
    return " · ".join(parts)


def persist_entity(fname, delta, allowed, message, log=None):
    """Delta write for leads/orgs/campaigns: pull -> apply -> commit -> push.

    Mirrors persist()/persist_followup() above: same pull-before-write, same
    push-then-retry-on-conflict. model.apply_delta raises KeyError on an
    unknown id, which do_POST turns into a 404.

    `log=(author, via)` — for lead edits, also append a Log line to comments.json in
    the same commit. A human edit is how the user "acts" on a lead, and the Today view
    drops a bot flag only once a non-bot Log entry postdates it; without this line,
    pressing Drop on a lead that is already dropped changed nothing visible.
    """
    with LOCK:
        git("pull", "--no-edit", "--no-rebase", "-q")
        items = load_json_file(fname, [])
        model.apply_delta(items, delta, allowed)   # raises KeyError on unknown id
        model.save(os.path.join(ROOT, fname), items)
        git("add", fname)
        if log and fname == "leads.json":
            comments = load_json_file("comments.json", [])
            comments.append({"key": delta["id"], "author": log[0], "via": log[1],
                             "text": _delta_text(delta),
                             "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            with open(os.path.join(ROOT, "comments.json"), "w", encoding="utf-8") as f:
                json.dump(comments, f, indent=1, ensure_ascii=False)
            git("add", "comments.json")
        git("-c", "user.name=Barebones CRM", "-c", "user.email=crm@localhost",
            "commit", "-q", "-m", message)
        if git("push", "-q", "origin", "main").returncode != 0:
            git("pull", "--no-edit", "--no-rebase", "-q"); git("push", "-q", "origin", "main")
        return items


def _slug(s):
    import re
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")[:60] or "x"


DEFAULT_STATES = [{"key": "prospect", "label": "Prospect", "kind": "active"},
                  {"key": "contacted", "label": "Contacted", "kind": "active"},
                  {"key": "replied", "label": "Replied", "kind": "active"},
                  {"key": "won", "label": "Won", "kind": "won"},
                  {"key": "lost", "label": "Lost", "kind": "lost"}]


UNMATCHED = os.path.join(ROOT, "inbox", "unmatched.json")


def _drop_unmatched(links):
    """Remove inbox/unmatched.json entries whose link is in `links`. Returns True if
    the file changed. Caller holds LOCK and does the git add/commit."""
    if not links:
        return False
    items = load_json_file("inbox/unmatched.json", [])
    kept = [u for u in items if u.get("link") not in links]
    if len(kept) == len(items):
        return False
    model.save(UNMATCHED, kept)
    return True


def persist_dismiss(links):
    """Drop unmatched entries the human chose not to promote."""
    with LOCK:
        git("pull", "--no-edit", "--no-rebase", "-q")
        if _drop_unmatched(set(links)):
            git("add", "inbox/unmatched.json")
            git("-c", "user.name=Barebones CRM", "-c", "user.email=crm@localhost",
                "commit", "-q", "-m", "dismiss: %d unmatched" % len(links))
            if git("push", "-q", "origin", "main").returncode != 0:
                git("pull", "--no-edit", "--no-rebase", "-q"); git("push", "-q", "origin", "main")
        return load_json_file("inbox/unmatched.json", [])


def persist_import(campaign_id, campaign_name, rows, default_state, dismiss_links=()):
    """Create leads (and their orgs) from imported CSV rows into a campaign, creating
    the campaign itself with default states if it doesn't exist yet (onboarding).

    Rows are dicts already mapped by the browser: {name, email, org, role, notes,
    sector, region, strength, linkedin}. Appends to organizations.json + leads.json (and
    campaigns.json if a campaign was created), dedups ids, validates the whole
    model, then commits + pushes. `dismiss_links`: unmatched entries to drop in the
    same commit (promote-from-unmatched).
    """
    with LOCK:
        git("pull", "--no-edit", "--no-rebase", "-q")
        campaigns = load_json_file("campaigns.json", [])
        camp = next((c for c in campaigns if c.get("id") == campaign_id), None)
        created_campaign = False
        if not camp:
            camp = {"id": campaign_id, "name": (campaign_name or campaign_id),
                    "targetType": "individual", "icp": "", "goal": "Engagement",
                    "states": [dict(s) for s in DEFAULT_STATES], "window": None, "notes": ""}
            campaigns.append(camp); created_campaign = True
        state_keys = {s["key"] for s in camp.get("states", [])}
        state = default_state if default_state in state_keys else (
            next(iter(state_keys)) if state_keys else "prospect")
        orgs = load_json_file("organizations.json", [])
        leads = load_json_file("leads.json", [])
        org_ids = {o["id"] for o in orgs}
        lead_ids = {l["id"] for l in leads}
        pfx = campaign_id + ":"
        added_leads = added_orgs = 0
        for r in rows:
            name = str(r.get("name", "")).strip()
            if not name:
                continue
            org_name = str(r.get("org", "")).strip() or name
            oid = pfx + _slug(org_name)
            if oid not in org_ids:
                orgs.append({"id": oid, "name": org_name,
                             "sector": str(r.get("sector", "")).strip() or "—",
                             "region": (str(r.get("region", "")).strip() or None),
                             "url": (r.get("url") or None), "campaignId": campaign_id})
                org_ids.add(oid); added_orgs += 1
            lid = base = pfx + _slug(name); i = 2
            while lid in lead_ids:
                lid = base + "-" + str(i); i += 1
            emails = [e.strip() for e in str(r.get("email", "")).replace(";", ",").split(",") if e.strip()]
            leads.append({"id": lid, "orgId": oid, "campaignId": campaign_id, "name": name,
                          "emails": emails,
                          "handles": ({"linkedin": str(r["linkedin"]).strip()} if r.get("linkedin") else {}),
                          "role": (str(r.get("role", "")).strip() or None), "state": state,
                          "strength": r.get("strength") if r.get("strength") in ("strong", "medium", "stretch") else "medium",
                          "followUpDate": None, "waiting": "them",
                          "facts": {"paidStatus": "free", "amount": None, "formatRequested": None,
                                    "formatSent": None, "physicalCopyOffered": False},
                          "gmailThreadId": None, "notes": str(r.get("notes", "")).strip()})
            lead_ids.add(lid); added_leads += 1
        # validate the whole model before writing anything
        cids = {c["id"] for c in campaigns}; oids = {o["id"] for o in orgs}
        cst = {c["id"]: {s["key"] for s in c["states"]} for c in campaigns}
        errs = []
        for o in orgs: errs += model.validate_org(o, cids)
        for l in leads: errs += model.validate_lead(l, oids, cst)
        if errs:
            raise ValueError("validation failed: " + "; ".join(errs[:5]))
        files = ["organizations.json", "leads.json"]
        model.save(os.path.join(ROOT, "organizations.json"), orgs)
        model.save(os.path.join(ROOT, "leads.json"), leads)
        if created_campaign:
            model.save(os.path.join(ROOT, "campaigns.json"), campaigns)
            files.append("campaigns.json")
        if _drop_unmatched(set(dismiss_links)):
            files.append("inbox/unmatched.json")
        git("add", *files)
        git("-c", "user.name=Barebones CRM", "-c", "user.email=crm@localhost",
            "commit", "-q", "-m", "import: %d leads into %s" % (added_leads, campaign_id))
        if git("push", "-q", "origin", "main").returncode != 0:
            git("pull", "--no-edit", "--no-rebase", "-q"); git("push", "-q", "origin", "main")
        return {"addedLeads": added_leads, "addedOrgs": added_orgs, "state": state,
                "createdCampaign": created_campaign, "campaignId": campaign_id}


def llm_answer(question, history, context):
    """Plain-English Q&A about the CRM. Read-only/advisory. Provider order:
    (1) a local Claude Code CLI (`claude -p`) if installed — uses the user's own logged-in
        session, so NO API key is needed; (2) ANTHROPIC_API_KEY (Claude) or (3) OPENAI_API_KEY
        (ChatGPT) over raw HTTP, keeping zero dependencies. Override the model with CRM_LLM_MODEL
        (and the CLI path with CRM_CLAUDE_BIN).
    """
    import urllib.request, shutil, tempfile
    system = (
        "You are a friendly assistant helping someone learn and operate 'barebonesCRM', a "
        "small file-based CRM. Data model: Campaigns contain Organizations which contain Leads. "
        "Each lead has a state (one of its campaign's states, each tagged active/won/lost), a "
        "followUpDate, and a 'waiting' side (me/them). The user works through a web UI with these "
        "views: Today (leads due or owed), Campaigns (funnels), People (a sortable table + a "
        "per-person detail with controls). Controls: set state, schedule the next touch (+N days), "
        "mark Won or Drop, and add dated Log notes. Explain the logic in plain English and tell the "
        "user which control to click. You are ADVISORY and READ-ONLY: you cannot change data. "
        "Here is a snapshot of their current data:\n" + context)
    msgs = (history or [])[-8:] + [{"role": "user", "content": question}]

    # (1) Local Claude Code CLI — the user's installed `claude`, no API key. Run from a temp
    # dir so it does not pick up this repo's CLAUDE.md; the question goes on stdin (no shell
    # injection); --append-system-prompt carries the CRM context.
    claude_bin = os.environ.get("CRM_CLAUDE_BIN") or shutil.which("claude") \
        or (os.path.expanduser("~/.local/bin/claude") if os.path.exists(os.path.expanduser("~/.local/bin/claude")) else None)
    if claude_bin:
        convo = "\n\n".join("%s: %s" % (m["role"], m["content"]) for m in msgs)
        cmd = [claude_bin, "-p", "--append-system-prompt", system]
        mid = os.environ.get("CRM_LLM_MODEL")
        if mid:
            cmd += ["--model", mid]
        try:
            r = subprocess.run(cmd, input=convo, capture_output=True, text=True,
                               timeout=180, cwd=tempfile.gettempdir())
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass  # fall through to the HTTP providers below

    ank = os.environ.get("ANTHROPIC_API_KEY")
    opk = os.environ.get("OPENAI_API_KEY")
    if ank:
        mid = os.environ.get("CRM_LLM_MODEL", "claude-opus-5")
        body = json.dumps({"model": mid, "max_tokens": 1500, "system": system,
                           "messages": msgs}).encode("utf-8")
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
              headers={"content-type": "application/json", "x-api-key": ank,
                       "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read())
        return ("".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text").strip()
                or "(the model returned no text)")
    if opk:
        mid = os.environ.get("CRM_LLM_MODEL", "gpt-4o")
        body = json.dumps({"model": mid, "max_tokens": 1500,
                           "messages": [{"role": "system", "content": system}] + msgs}).encode("utf-8")
        req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=body,
              headers={"content-type": "application/json", "authorization": "Bearer " + opk})
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read())
        return d["choices"][0]["message"]["content"].strip()
    return ("No assistant available. Install Claude Code (the `claude` CLI) to use your own "
            "logged-in session with no API key, or export ANTHROPIC_API_KEY / OPENAI_API_KEY "
            "before starting crm.py, then reload.")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def end_headers(self):
        # index.html carries the status snapshots and is rewritten every morning by
        # the digest bot (and by hand). Without an explicit header the browser applies
        # heuristic caching and silently serves yesterday's board — a stale CRM that
        # looks current is worse than one that fails loudly.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _via(self):
        # Provenance. `via` is derived from request headers, not from the payload, so a
        # script cannot claim to be you by passing author:"the user" — the header pair is
        # what decides. Browser fetch() sends a same-origin Referer and a Mozilla UA;
        # curl/agents send neither. Default author follows: UI posts are yours, anything
        # else is Claude. (Entries with no `via` field predate this and are unknown.)
        ua = self.headers.get("User-Agent", "")
        ref = self.headers.get("Referer", "")
        origins = ("http://localhost:%d" % PORT, "http://127.0.0.1:%d" % PORT)
        return "ui" if ref.startswith(origins) and "Mozilla" in ua else "api"

    def _ask_context(self, lead_id=None):
        """A compact snapshot of the model for the assistant to reason over."""
        camps = load_json_file("campaigns.json", [])
        leads = load_json_file("leads.json", [])
        orgs = {o["id"]: o for o in load_json_file("organizations.json", [])}
        lines = []
        for c in camps:
            cl = [l for l in leads if l.get("campaignId") == c["id"]]
            by = {}
            for l in cl:
                by[l.get("state")] = by.get(l.get("state"), 0) + 1
            lines.append("- %s (%s): %d leads; by state %s; goal: %s"
                         % (c.get("name"), c.get("id"), len(cl), by, c.get("goal", "")))
        ctx = "Campaigns:\n" + "\n".join(lines) + "\nTotals: %d leads, %d orgs." % (len(leads), len(orgs))
        if lead_id:
            l = next((x for x in leads if x.get("id") == lead_id), None)
            if l:
                o = orgs.get(l.get("orgId"), {})
                ctx += ("\n\nFocused lead: %s at %s — campaign %s, state %s, waiting %s, "
                        "followUp %s, notes: %s" % (l.get("name"), o.get("name", ""),
                        l.get("campaignId"), l.get("state"), l.get("waiting"),
                        l.get("followUpDate"), (l.get("notes", "") or "")[:200]))
        return ctx

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/comments":
            return self._json(load())
        if p == "/followups":
            return self._json(load_followups())
        if p == "/campaigns":
            return self._json(load_json_file("campaigns.json", []))
        if p == "/organizations":
            return self._json(load_json_file("organizations.json", []))
        if p == "/leads":
            return self._json(load_json_file("leads.json", []))
        if p == "/trail":
            return self._json(load_json_file("trail.json", {}))
        if p == "/observations":
            return self._json(load_json_file("observations.json", {}))
        if p == "/unmatched":
            return self._json(load_json_file("inbox/unmatched.json", []))
        return super().do_GET()

    def do_POST(self):
        p = urlparse(self.path).path
        if p == "/followup":
            return self._do_followup()
        if p in ENTITY:
            try:
                n = int(self.headers.get("Content-Length", 0))
                delta = json.loads(self.rfile.read(n))
                assert str(delta.get("id", "")).strip()
            except Exception:
                return self._json({"error": "bad request"}, 400)
            fname, allowed = ENTITY[p]
            via = self._via()
            try:
                return self._json(persist_entity(fname, delta, allowed,
                                  f"{p[1:]}: {delta['id']} ({via})",
                                  log=("Yoel" if via == "ui" else "Claude", via)))
            except KeyError:
                return self._json({"error": "unknown id"}, 404)
            except Exception as e:
                return self._json({"error": str(e)}, 500)
        if p == "/import":
            try:
                n = int(self.headers.get("Content-Length", 0))
                c = json.loads(self.rfile.read(n))
                cid = str(c.get("campaignId", "")).strip()
                rows = c.get("rows") or []
                assert cid and isinstance(rows, list) and rows
            except Exception:
                return self._json({"error": "bad request"}, 400)
            try:
                return self._json(persist_import(cid, str(c.get("campaignName", "")).strip(),
                                                 rows, str(c.get("defaultState", "")).strip(),
                                                 [str(x) for x in (c.get("dismissLinks") or [])]))
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            except Exception as e:
                return self._json({"error": str(e)}, 500)
        if p == "/dismiss":
            try:
                n = int(self.headers.get("Content-Length", 0))
                links = json.loads(self.rfile.read(n)).get("links") or []
                assert isinstance(links, list) and links
            except Exception:
                return self._json({"error": "bad request"}, 400)
            return self._json(persist_dismiss([str(x) for x in links]))
        if p == "/ask":
            try:
                n = int(self.headers.get("Content-Length", 0))
                c = json.loads(self.rfile.read(n))
                q = str(c.get("question", "")).strip()
                assert q
            except Exception:
                return self._json({"error": "bad request"}, 400)
            try:
                ctx = self._ask_context(c.get("leadId"))
                return self._json({"answer": llm_answer(q, c.get("history"), ctx)})
            except Exception as e:
                return self._json({"answer": "Assistant error: %s" % e})
        if p != "/comment":
            return self._json({"error": "not found"}, 404)
        try:
            n = int(self.headers.get("Content-Length", 0))
            c = json.loads(self.rfile.read(n))
            assert str(c.get("key", "")).strip() and str(c.get("text", "")).strip()
        except Exception:
            return self._json({"error": "bad request"}, 400)
        via = self._via()
        entry = {
            "key": str(c["key"]).strip()[:200],
            "author": (str(c.get("author") or "").strip() or ("You" if via == "ui" else "Claude"))[:60],
            "via": via,
            "text": str(c["text"]).strip()[:2000],
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        try:
            return self._json(persist(entry))
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _do_followup(self):
        """POST /followup {key, followUpDate} — "YYYY-MM-DD" to set, "" or null to clear.

        Still accepts the old short name `fu`. Renamed 2026-08-14: the user could not tell
        what `fu` meant, and a field nobody can read is a field nobody can trust.
        """
        try:
            n = int(self.headers.get("Content-Length", 0))
            c = json.loads(self.rfile.read(n))
            key = str(c.get("key", "")).strip()[:200]
            followUpDate = str(c.get("followUpDate") or c.get("fu") or "").strip()[:10]
            closed = bool(c.get("closed"))
            reopen = bool(c.get("reopen"))
            assert key
            # Reject anything that is not a plain calendar date: a malformed value here
            # would render as "Invalid Date" on the board and quietly stop the row from
            # ever coming due again — a silent miss is worse than a rejected click.
            if followUpDate and not closed:
                time.strptime(followUpDate, "%Y-%m-%d")
        except Exception:
            return self._json({"error": "bad request"}, 400)
        via = self._via()
        author = (str(c.get("author") or "").strip() or ("You" if via == "ui" else "Claude"))[:60]
        try:
            return self._json(persist_followup(key, followUpDate, author, via, closed, reopen))
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    os.chdir(ROOT)
    print("Barebones CRM: http://localhost:%d/app.html" % PORT)
    print("Comments save to comments.json and auto-commit+push. Ctrl-C to stop.")
    try:
        http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
