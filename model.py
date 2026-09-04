# model.py
import json

STATES_KINDS = {"active", "won", "lost"}
PAID = {"free", "paid", "vendor-placed", "unknown"}
FORMATS = {None, "epub", "pdf", "physical"}
WAITING = {"me", "them"}
STRENGTH = {"strong", "medium", "stretch"}

def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def save(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)

def validate_campaign(c):
    errs = []
    for k in ("id", "name", "targetType", "goal", "states"):
        if not c.get(k):
            errs.append(f"campaign missing {k}")
    if c.get("targetType") not in ("individual", "organization"):
        errs.append("campaign.targetType must be individual|organization")
    states = c.get("states") or []
    if not any(s.get("kind") == "won" for s in states):
        errs.append("campaign needs at least one 'won' state (the goal)")
    for s in states:
        if s.get("kind") not in STATES_KINDS:
            errs.append(f"state {s.get('key')!r} bad kind {s.get('kind')!r}")
    return errs

def validate_org(o, campaign_ids):
    errs = []
    if not o.get("id"): errs.append("org missing id")
    if not o.get("name"): errs.append("org missing name")
    cid = o.get("campaignId")
    if cid is not None and cid not in campaign_ids:
        errs.append(f"org.campaignId {cid!r} not a known campaign")
    return errs

def validate_lead(l, org_ids, campaign_states):
    errs = []
    if not l.get("id"): errs.append("lead missing id")
    if l.get("orgId") not in org_ids:
        errs.append(f"lead.orgId {l.get('orgId')!r} is not a known org")
    cid = l.get("campaignId")
    if cid not in campaign_states:
        errs.append(f"lead.campaignId {cid!r} is not a known campaign")
    elif l.get("state") not in campaign_states[cid]:
        errs.append(f"lead.state {l.get('state')!r} not in campaign {cid} states")
    if l.get("waiting") not in WAITING:
        errs.append("lead.waiting must be me|them")
    if l.get("strength") not in STRENGTH:
        errs.append("lead.strength must be strong|medium|stretch")
    f = l.get("facts") or {}
    if f.get("paidStatus") not in PAID:
        errs.append("facts.paidStatus invalid")
    if f.get("formatRequested") not in FORMATS or f.get("formatSent") not in FORMATS:
        errs.append("facts.format* must be epub|pdf|physical|null")
    return errs

def apply_delta(items, delta, allowed_fields):
    key = delta["id"]
    for it in items:
        if it.get("id") == key:
            for f, v in delta.items():
                if f == "id" or f not in allowed_fields:
                    continue
                if f == "facts" and isinstance(v, dict) and isinstance(it.get("facts"), dict):
                    it["facts"].update(v)
                else:
                    it[f] = v
            return items
    raise KeyError(key)
