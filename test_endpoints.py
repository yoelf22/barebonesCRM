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

if __name__ == "__main__":
    test_get_leads_ok(); print("ok")
