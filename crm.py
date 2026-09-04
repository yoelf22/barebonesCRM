#!/usr/bin/env python3
"""
Barebones CRM launcher.

Serves the CRM at http://localhost:8787/index.html AND persists per-contact
comments back to the repo:
  - GET  /comments        -> comments.json contents
  - POST /comment {key,text[,author]} -> append + git commit + push
  - GET  /followups       -> followups.json contents (human-chosen follow-up dates)
  - POST /followup {key,followUpDate} -> set/clear + git commit + push
                   {key,closed:true}   -> close the item (off the board) + same
                   {key,reopen:true}   -> undo a close, restoring any date it carried
                          (also accepts the old short name `fu`)

Comments live in comments.json (kept out of index.html so they can never break
the page). Each save pulls the bot's latest, commits comments.json only, and
pushes, so the repo stays the single source of truth.

Run:  python3 crm.py     (Ctrl-C to stop)
"""
import http.server, json, os, subprocess, threading, time
from urllib.parse import urlparse
import model

ROOT = os.path.dirname(os.path.abspath(__file__))
COMMENTS = os.path.join(ROOT, "comments.json")
FOLLOWUPS = os.path.join(ROOT, "followups.json")
PORT = 8787
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


def persist_entity(fname, delta, allowed, message):
    """Delta write for leads/orgs/campaigns: pull -> apply -> commit -> push.

    Mirrors persist()/persist_followup() above: same pull-before-write, same
    push-then-retry-on-conflict. model.apply_delta raises KeyError on an
    unknown id, which do_POST turns into a 404.
    """
    with LOCK:
        git("pull", "--no-edit", "--no-rebase", "-q")
        items = load_json_file(fname, [])
        model.apply_delta(items, delta, allowed)   # raises KeyError on unknown id
        model.save(os.path.join(ROOT, fname), items)
        git("add", fname)
        git("-c", "user.name=Barebones CRM", "-c", "user.email=crm@localhost",
            "commit", "-q", "-m", message)
        if git("push", "-q", "origin", "main").returncode != 0:
            git("pull", "--no-edit", "--no-rebase", "-q"); git("push", "-q", "origin", "main")
        return items


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
            try:
                return self._json(persist_entity(fname, delta, allowed,
                                  f"{p[1:]}: {delta['id']} ({self._via()})"))
            except KeyError:
                return self._json({"error": "unknown id"}, 404)
            except Exception as e:
                return self._json({"error": str(e)}, 500)
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
