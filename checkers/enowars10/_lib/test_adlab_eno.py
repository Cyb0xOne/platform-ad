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
