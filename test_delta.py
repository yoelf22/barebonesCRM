# test_delta.py
import model

LEADS = [{"id":"jane","state":"prospect","followUpDate":None,
          "facts":{"paidStatus":"unknown","formatSent":None},"notes":""}]
ALLOWED = {"state","followUpDate","waiting","notes","facts"}

def test_merges_allowed_field():
    out = model.apply_delta(LEADS, {"id":"jane","state":"replied"}, ALLOWED)
    assert out[0]["state"] == "replied"

def test_facts_deep_merge():
    out = model.apply_delta(LEADS, {"id":"jane","facts":{"formatSent":"pdf"}}, ALLOWED)
    assert out[0]["facts"]["formatSent"] == "pdf"
    assert out[0]["facts"]["paidStatus"] == "unknown"  # untouched key survives

def test_disallowed_field_ignored():
    out = model.apply_delta(LEADS, {"id":"jane","orgId":"HACK"}, ALLOWED)
    assert "orgId" not in out[0]

def test_unknown_id_raises():
    try:
        model.apply_delta(LEADS, {"id":"ghost","state":"x"}, ALLOWED)
        assert False, "expected KeyError"
    except KeyError:
        pass

if __name__ == "__main__":
    test_merges_allowed_field(); test_facts_deep_merge()
    test_disallowed_field_ignored(); test_unknown_id_raises()
    print("ok")
