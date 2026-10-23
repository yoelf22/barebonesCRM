# test_endpoints.py  — starts the server on a throwaway port, hits it, shuts down
import json, threading, urllib.request, http.server, importlib
crm = importlib.import_module("crm")

def _get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as r:
        return r.status, json.loads(r.read())

def test_get_leads_ok():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), crm.Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        code, body = _get(port, "/leads")
        assert code == 200 and isinstance(body, list)
        code, body = _get(port, "/campaigns")
        assert code == 200 and isinstance(body, list)
    finally:
        srv.shutdown()


def test_promote_and_dismiss(tmp=None):
    # runs against a scratch copy of the repo so no real file or git remote is touched
    import os, shutil, tempfile, subprocess
    d = tempfile.mkdtemp(); root = crm.ROOT
    for f in ("crm.py","model.py","campaigns.json","organizations.json","leads.json","comments.json","followups.json","observations.json","trail.json"):
        shutil.copy(os.path.join(root, f), d)
    os.makedirs(os.path.join(d, "inbox")); subprocess.run(["git","-C",d,"init","-q"])
    unm = [{"from":"sam@example.com","name":"Sam Example","subject":"Re: talk","date":"2026-09-04T05:40:56Z",
            "link":"https://mail.example/1","channel":"email","guessOrg":"Somewhere"},
           {"from":"https://linkedin.com/in/pat","name":"Pat Example","subject":"","date":"2026-09-04T05:41:00Z",
            "link":"https://linkedin.example/2","channel":"linkedin","guessOrg":"-"}]
    json.dump(unm, open(os.path.join(d, "inbox", "unmatched.json"), "w"))
    crm.ROOT = d; crm.UNMATCHED = os.path.join(d, "inbox", "unmatched.json")
    try:
        r = crm.persist_import("outreach", "", [{"name":"Sam Example","email":"sam@example.com","org":"Somewhere"}],
                               "prospect", ["https://mail.example/1"])
        assert r["addedLeads"] == 1 and r["addedOrgs"] == 1
        left = json.load(open(crm.UNMATCHED)); assert [u["name"] for u in left] == ["Pat Example"]
        r = crm.persist_import("outreach", "", [{"name":"Pat Example","linkedin":"https://linkedin.com/in/pat"}], "prospect", ["https://linkedin.example/2"])
        lead = [l for l in json.load(open(os.path.join(d, "leads.json"))) if l["name"] == "Pat Example"][0]
        assert lead["handles"] == {"linkedin": "https://linkedin.com/in/pat"}
        assert json.load(open(crm.UNMATCHED)) == []
        json.dump(unm[:1], open(crm.UNMATCHED, "w"))
        assert crm.persist_dismiss(["https://mail.example/1"]) == []
    finally:
        crm.ROOT = root; crm.UNMATCHED = os.path.join(root, "inbox", "unmatched.json"); shutil.rmtree(d)

def test_lead_save_logs_user_action():
    # a human /lead write (state, date, waiting…) leaves a dated Log line, so the Today
    # view can tell the user has acted on a bot flag — even when the value is unchanged
    import os, shutil, tempfile, subprocess
    d = tempfile.mkdtemp(); root = crm.ROOT
    for f in ("campaigns.json","organizations.json","leads.json","comments.json"):
        shutil.copy(os.path.join(root, f), d)
    subprocess.run(["git","-C",d,"init","-q"]); crm.ROOT = d
    try:
        lid = json.load(open(os.path.join(d, "leads.json")))[0]["id"]
        crm.persist_entity("leads.json", {"id": lid, "waiting": "me"}, crm.ENTITY["/lead"][1], "t", log=("You", "ui"))
        c = json.load(open(os.path.join(d, "comments.json")))[-1]
        assert c["key"] == lid and c["via"] == "ui" and c["author"] == "You" and c["text"] == "waiting → me", c
        assert crm._delta_text({"id": lid, "state": "lost"}) == "state → lost"
        assert crm._delta_text({"id": lid, "followUpDate": None}) == "follow-up cleared"
        assert crm._delta_text({"id": lid, "notes": "long text"}) == "notes updated"
    finally:
        crm.ROOT = root; shutil.rmtree(d)

def test_lead_write_validated_and_told_feed():
    # a bad value on /lead is refused up front (not left to break a later /import), and
    # facts.told feeds the Ask context with who was told and which warm leads were not
    import os, shutil, tempfile, subprocess
    d = tempfile.mkdtemp(); root = crm.ROOT
    for f in ("campaigns.json","organizations.json","leads.json","comments.json","observations.json"):
        shutil.copy(os.path.join(root, f), d)
    subprocess.run(["git","-C",d,"init","-q"]); crm.ROOT = d
    try:
        leads = json.load(open(os.path.join(d, "leads.json"))); lid = leads[0]["id"]
        try:
            crm.persist_entity("leads.json", {"id": lid, "state": "no-such-state"}, crm.ENTITY["/lead"][1], "t")
            assert False, "bad state was saved"
        except ValueError as e:
            assert lid in str(e) and "no-such-state" in str(e)
        assert json.load(open(os.path.join(d, "leads.json"))) == leads
        crm.persist_entity("leads.json", {"id": lid, "facts": {"told": {"news": {"date": "2026-10-01", "kind": "email"}}}},
                           crm.ENTITY["/lead"][1], "t")
        ctx = crm.Handler._ask_context(None)
        assert "Communication 'news' \u2014 told 1:" in ctx and leads[0]["name"] in ctx, ctx[-600:]
    finally:
        crm.ROOT = root; shutil.rmtree(d)

if __name__ == "__main__":
    test_get_leads_ok(); test_promote_and_dismiss(); test_lead_save_logs_user_action(); test_lead_write_validated_and_told_feed(); print("ok")
