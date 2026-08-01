import asyncio
import importlib
import json
import os
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

_ = os.environ.setdefault(
    "FORCAD_DSN",
    "postgresql://test:test@localhost:5432/forcad_test",
)

admin_app = importlib.import_module("admin_app")


class FakeCursor:
    def __init__(self, *results: Any):
        self.results = list(results)
        self.calls: list[tuple[str, object]] = []

    def execute(self, query: str, params: object = None) -> None:
        self.calls.append((query, params))

    def fetchall(self) -> Any:
        return self.results.pop(0)

    def fetchone(self) -> Any:
        return self.results.pop(0)


@contextmanager
def use_cursor(fake: FakeCursor):
    yield fake


def asgi_request(
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
) -> tuple[int, bytes]:
    body = json.dumps(payload).encode() if payload is not None else b""
    messages: list[dict[str, Any]] = []
    request_sent = False

    async def receive() -> dict[str, Any]:
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    asyncio.run(admin_app.app(scope, receive, send))
    start = next(
        message for message in messages
        if message["type"] == "http.response.start"
    )
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return start["status"], response_body


class AuthorizedKeyApiTest(unittest.TestCase):
    key_data = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    public_key = f"ssh-ed25519 {key_data} alice@example.com"

    def test_post_rejects_invalid_public_keys(self) -> None:
        invalid_keys = (
            "",
            f"{self.public_key}\n{self.public_key}",
            f"ssh-dss {self.key_data} alice@example.com",
        )

        with patch.object(admin_app, "_vm_ssh", create=True) as vm_ssh:
            for key in invalid_keys:
                with self.subTest(key=key):
                    status, _ = asgi_request(
                        "POST",
                        "/api/admin/team/7/authorized_key",
                        {"key": key},
                    )
                    self.assertEqual(status, 400)

        vm_ssh.assert_not_called()

    def test_post_returns_404_for_unknown_team(self) -> None:
        fake = FakeCursor(None)
        with (
            patch.object(admin_app, "cursor", lambda: use_cursor(fake)),
            patch.object(admin_app, "_vm_ssh", create=True) as vm_ssh,
        ):
            status, body = asgi_request(
                "POST",
                "/api/admin/team/404/authorized_key",
                {"key": self.public_key},
            )

        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body), {"detail": "Tim tidak ditemukan."})
        self.assertEqual(
            fake.calls,
            [("SELECT name, ip FROM teams WHERE id = %s", (404,))],
        )
        vm_ssh.assert_not_called()

    def test_post_maps_successful_ssh_result(self) -> None:
        fake = FakeCursor({"name": "Athena", "ip": "10.13.37.11"})
        result = SimpleNamespace(returncode=0, stdout="3\n", stderr="")
        remote = (
            "export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; "
            "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && "
            "sort -u -o ~/.ssh/authorized_keys ~/.ssh/authorized_keys && "
            "chmod 600 ~/.ssh/authorized_keys && wc -l < ~/.ssh/authorized_keys"
        )
        with (
            patch.object(admin_app, "cursor", lambda: use_cursor(fake)),
            patch.object(admin_app, "_vm_ssh", return_value=result, create=True) as vm_ssh,
            patch.object(admin_app, "VM_SSH_USER", "team", create=True),
        ):
            status, body = asgi_request(
                "POST",
                "/api/admin/team/7/authorized_key",
                {"key": self.public_key},
            )

        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {
            "ok": True,
            "team": "Athena",
            "ip": "10.13.37.11",
            "user": "team",
            "total_keys": "3",
        })
        vm_ssh.assert_called_once_with(
            "10.13.37.11",
            remote,
            stdin=self.public_key + "\n",
        )

    def test_get_parses_authorized_keys(self) -> None:
        fake = FakeCursor({"name": "Athena", "ip": "10.13.37.11"})
        result = SimpleNamespace(
            returncode=0,
            stdout=(
                f'from="10.0.0.1" ssh-ed25519 {self.key_data} alice laptop\n'
                "not-a-key\n"
            ),
            stderr="",
        )
        remote = (
            "export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; "
            "cat ~/.ssh/authorized_keys 2>/dev/null || true"
        )
        with (
            patch.object(admin_app, "cursor", lambda: use_cursor(fake)),
            patch.object(admin_app, "_vm_ssh", return_value=result, create=True) as vm_ssh,
            patch.object(admin_app, "VM_SSH_USER", "team", create=True),
        ):
            status, body = asgi_request(
                "GET",
                "/api/admin/team/7/authorized_keys",
            )

        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {
            "team": "Athena",
            "ip": "10.13.37.11",
            "user": "team",
            "keys": [{
                "type": "ssh-ed25519",
                "comment": "alice laptop",
                "fingerprint": (
                    "SHA256:PrG9Q5lH63YpmOVmzMLgmceREYsvQFecxPfaK1Bht/k"
                ),
            }],
        })
        vm_ssh.assert_called_once_with("10.13.37.11", remote)


class AdminTeamsApiTest(unittest.TestCase):
    def test_teams_returns_rows_ordered_by_id(self) -> None:
        rows = [
            {"team_id": 7, "team": "Athena", "ip": "10.13.37.11"},
            {"team_id": 8, "team": "Ares", "ip": "10.13.37.12"},
        ]
        fake = FakeCursor(rows)
        with patch.object(admin_app, "cursor", lambda: use_cursor(fake)):
            status, body = asgi_request("GET", "/api/admin/teams")

        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), rows)
        self.assertEqual(
            fake.calls,
            [("SELECT id AS team_id, name AS team, ip FROM teams ORDER BY id", None)],
        )


if __name__ == "__main__":
    unittest.main()
