import adlab_eno as A
from checklib import Status

def test_state_roundtrip():
    s = A.encode_state(u="alice", p="pw123", rid="42")
    assert A.decode_state(s) == {"u": "alice", "p": "pw123", "rid": "42"}

def test_state_compact_single_line():
    assert "\n" not in A.encode_state(u="x")

def test_decode_bad_raises_valueerror():
    import pytest
    with pytest.raises(ValueError):
        A.decode_state("bukan json")

def test_rand_unique_enough():
    assert len({A.rand_username() for _ in range(200)}) > 190

def test_status_for_connection_error_is_down():
    assert A.status_for(ConnectionError()) == Status.DOWN
    assert A.status_for(TimeoutError()) == Status.DOWN
    assert A.status_for(OSError()) == Status.DOWN

def test_status_for_assertion_is_mumble():
    assert A.status_for(AssertionError()) == Status.MUMBLE
    assert A.status_for(KeyError()) == Status.MUMBLE

def test_http_session_has_base():
    s = A.http("1.2.3.4", 8000)
    assert s.base == "http://1.2.3.4:8000"

def test_status_for_requests_httperror_is_mumble():
    import requests
    assert A.status_for(requests.exceptions.HTTPError()) == Status.MUMBLE

def test_status_for_json_decode_is_mumble():
    # requests.JSONDecodeError adalah OSError DAN ValueError sekaligus;
    # harus MUMBLE, bukan DOWN.
    import requests
    try:
        exc = requests.exceptions.JSONDecodeError("x", "y", 0)
    except TypeError:
        import json
        exc = json.JSONDecodeError("x", "y", 0)
    assert A.status_for(exc) == Status.MUMBLE

def test_status_for_requests_connection_is_down():
    import requests
    assert A.status_for(requests.exceptions.ConnectionError()) == Status.DOWN

def test_http_leading_slash_resolves_through_base():
    import threading, http.server
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(self.path.encode())
        def log_message(self, *a): pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    threading.Thread(target=srv.handle_request, daemon=True).start()
    s = A.http("127.0.0.1", port)
    r = s.get("/hello")
    srv.server_close()
    assert r.text == "/hello"
