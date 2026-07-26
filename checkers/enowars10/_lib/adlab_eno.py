import json, random, socket, string
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from checklib import Status

_ADJ = ["Able", "Brave", "Calm", "Deft", "Eager", "Fair", "Glad", "Keen"]
_NOUN = ["Otter", "Falcon", "Cedar", "Quartz", "Maple", "Heron", "Comet"]

def rand_username():
    return random.choice(_ADJ) + random.choice(_NOUN) + str(random.randint(1000, 9999))

def rand_password():
    return "".join(random.choices(string.ascii_letters + string.digits, k=16))

def rand_text(n=24):
    return "".join(random.choices(string.ascii_letters + " ", k=n)).strip()

def encode_state(**kw):
    return json.dumps(kw, separators=(",", ":"))

def decode_state(s):
    d = json.loads(s)               # json.loads melempar ValueError untuk input tak sah
    if not isinstance(d, dict):
        raise ValueError("state bukan objek")
    return d

def http(host, port, timeout=10.0):
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=0.2, status_forcelist=[502, 503, 504])
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.base = f"http://{host}:{port}"
    orig = s.request
    def _req(method, url, **kw):
        kw.setdefault("timeout", timeout)
        if url.startswith("/"):
            url = s.base + url
        return orig(method, url, **kw)
    s.request = _req
    return s

class LineClient:
    def __init__(self, host, port, timeout=10.0):
        self.s = socket.create_connection((host, port), timeout=timeout)
        self.s.settimeout(timeout)
        self.buf = b""
    def sendline(self, b):
        if isinstance(b, str): b = b.encode()
        self.s.sendall(b + b"\n")
    def recv_until(self, delim):
        while delim not in self.buf:
            chunk = self.s.recv(4096)
            if not chunk: break
            self.buf += chunk
        i = self.buf.find(delim)
        if i < 0:
            out, self.buf = self.buf, b""
            return out
        out = self.buf[:i + len(delim)]; self.buf = self.buf[i + len(delim):]
        return out
    def recv(self, n=4096):
        if self.buf:
            out, self.buf = self.buf[:n], self.buf[n:]; return out
        return self.s.recv(n)
    def close(self):
        try: self.s.close()
        except OSError: pass

def status_for(exc):
    if isinstance(exc, (ConnectionError, TimeoutError, OSError,
                        requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout)):
        return Status.DOWN
    if isinstance(exc, (AssertionError, KeyError, ValueError, IndexError)):
        return Status.MUMBLE
    return Status.ERROR
