# test_model.py
import model
import tempfile
import os

CAMPAIGNS = [{"id":"academics","name":"Academics","targetType":"individual",
              "icp":"singled-out profs","goal":"inspection copy adopted",
              "states":[{"key":"prospect","label":"No reply","kind":"active"},
                        {"key":"replied","label":"Replied","kind":"active"},
                        {"key":"adopted","label":"Adopted","kind":"won"},
                        {"key":"passed","label":"Declined","kind":"lost"}]}]
ORGS = [{"id":"example-u","name":"Example University","sector":"Academic","region":"Europe",
         "url":None,"campaignId":"academics"}]

def test_valid_lead_passes():
    campaign_states = {"academics":{"prospect","replied","adopted","passed"}}
    lead = {"id":"jane","orgId":"example-u","campaignId":"academics",
            "name":"Jane Doe","emails":["jane@example.com"],
            "handles":{},"role":None,"state":"replied","strength":"medium",
            "followUpDate":None,"waiting":"them",
            "facts":{"paidStatus":"free","amount":None,"formatRequested":None,
                     "formatSent":"pdf","physicalCopyOffered":False},
            "gmailThreadId":"19fc71d99954ea27","notes":""}
    assert model.validate_lead(lead, {"example-u"}, campaign_states) == []

def test_bad_state_rejected():
    campaign_states = {"academics":{"prospect","replied"}}
    lead = {"id":"x","orgId":"example-u","campaignId":"academics","name":"X",
            "emails":["x@y.z"],"handles":{},"role":None,"state":"NOPE",
            "strength":"medium","followUpDate":None,"waiting":"them",
            "facts":{"paidStatus":"free","amount":None,"formatRequested":None,
                     "formatSent":None,"physicalCopyOffered":False},
            "gmailThreadId":None,"notes":""}
    errs = model.validate_lead(lead, {"example-u"}, campaign_states)
    assert any("state" in e for e in errs), errs

def test_unknown_org_rejected():
    campaign_states = {"academics":{"prospect"}}
    lead = {"id":"x","orgId":"ghost","campaignId":"academics","name":"X",
            "emails":["x@y.z"],"handles":{},"role":None,"state":"prospect",
            "strength":"medium","followUpDate":None,"waiting":"them",
            "facts":{"paidStatus":"unknown","amount":None,"formatRequested":None,
                     "formatSent":None,"physicalCopyOffered":False},
            "gmailThreadId":None,"notes":""}
    errs = model.validate_lead(lead, {"example-u"}, campaign_states)
    assert any("org" in e.lower() for e in errs), errs

def test_lead_with_empty_emails_passes():
    campaign_states = {"academics":{"prospect"}}
    lead = {"id":"x","orgId":"example-u","campaignId":"academics","name":"X",
            "emails":[],"handles":{},"role":None,"state":"prospect",
            "strength":"medium","followUpDate":None,"waiting":"them",
            "facts":{"paidStatus":"unknown","amount":None,"formatRequested":None,
                     "formatSent":None,"physicalCopyOffered":False},
            "gmailThreadId":None,"notes":""}
    assert model.validate_lead(lead, {"example-u"}, campaign_states) == []

def test_campaign_needs_one_won_state():
    bad = dict(CAMPAIGNS[0]); bad = {**bad, "states":[{"key":"a","label":"A","kind":"active"}]}
    assert any("won" in e for e in model.validate_campaign(bad))

def test_valid_org_passes():
    assert model.validate_org(ORGS[0], {"academics"}) == []

def test_unknown_campaign_rejected():
    bad_org = {"id":"test","name":"Test Org","campaignId":"ghost"}
    errs = model.validate_org(bad_org, {"academics"})
    assert any("campaign" in e.lower() for e in errs), errs

def test_load_save_roundtrip():
    data = {"key":"value","unicode":"café"}
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        temp_path = f.name
    try:
        model.save(temp_path, data)
        loaded = model.load(temp_path)
        assert loaded == data
    finally:
        os.unlink(temp_path)

if __name__ == "__main__":
    test_valid_lead_passes(); test_bad_state_rejected()
    test_unknown_org_rejected(); test_lead_with_empty_emails_passes()
    test_campaign_needs_one_won_state()
    test_valid_org_passes(); test_unknown_campaign_rejected()
    test_load_save_roundtrip()
    print("ok")
