import asyncio
import importlib
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Protocol, cast
from unittest.mock import patch

_ = os.environ.setdefault(
    "FORCAD_DSN",
    "postgresql://test:test@localhost:5432/forcad_test",
)

admin_app = importlib.import_module("admin_app")


class ControlOutcome(Protocol):
    timed_out: bool
    exit_code: int | None


def asgi_request(method: str, path: str) -> tuple[int, bytes]:
    messages: list[dict[str, Any]] = []
    request_sent = False

    async def receive() -> dict[str, Any]:
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": b"", "more_body": False}

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
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    asyncio.run(admin_app.app(scope, receive, send))
    start = next(message for message in messages if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return start["status"], body


class ControlRunnerTest(unittest.TestCase):
    def test_each_action_uses_fixed_ssh_argv_and_timeout(self) -> None:
        runner = cast(
            Callable[[str], ControlOutcome] | None,
            getattr(admin_app, "run_control", None),
        )
        if runner is None:
            self.fail("run_control is not implemented")
        completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")

        for action, timeout in (("start", 600), ("pause", 60), ("resume", 60)):
            with self.subTest(action=action):
                with (
                    patch.object(admin_app, "CONTROL_KEY", "/tmp/control-key"),
                    patch.object(admin_app, "CONTROL_USER", "operator"),
                    patch.object(admin_app, "CONTROL_HOST", "control-host"),
                    patch.object(
                        admin_app.subprocess,
                        "run",
                        return_value=completed,
                    ) as run,
                ):
                    runner(action)

                    run.assert_called_once_with(
                        [
                            "ssh",
                            "-i",
                            "/tmp/control-key",
                            "-o",
                            "BatchMode=yes",
                            "-o",
                            "IdentitiesOnly=yes",
                            "-o",
                            "ConnectTimeout=8",
                            "-o",
                            "StrictHostKeyChecking=accept-new",
                            "operator@control-host",
                            action,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                    )

    def test_subprocess_timeout_becomes_timeout_outcome(self) -> None:
        runner = cast(
            Callable[[str], ControlOutcome] | None,
            getattr(admin_app, "run_control", None),
        )
        if runner is None:
            self.fail("run_control is not implemented")

        with patch.object(
            admin_app.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["ssh"], 60),
        ):
            result = runner("pause")

        self.assertTrue(result.timed_out)
        self.assertIsNone(result.exit_code)


class ControlApiTest(unittest.TestCase):
    history_path = ""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.history_path = str(Path(temporary.name) / "control-history.jsonl")

    def test_invalid_action_returns_422_without_calling_runner(self) -> None:
        with (
            patch.object(admin_app, "run_control", create=True) as runner,
            patch.object(
                admin_app,
                "CONTROL_HISTORY_PATH",
                self.history_path,
                create=True,
            ),
        ):
            status, _ = asgi_request("POST", "/api/admin/control/restart")

        self.assertEqual(status, 422)
        runner.assert_not_called()
        self.assertFalse(Path(self.history_path).exists())

    def test_exit_codes_and_timeout_map_to_http_and_one_audit_record(self) -> None:
        cases = (
            ("start", 0, False, "ok", 200, "ForcAD started"),
            ("pause", 75, False, "busy", 409, "another action"),
            ("resume", 1, False, "failed", 502, " leading-" + "x" * 510 + "  "),
            ("pause", None, True, "timeout", 504, "deadline"),
            ("start", 64, False, "failed", 500, "invalid wrapper token"),
        )

        for action, exit_code, timed_out, outcome, expected_status, stderr in cases:
            with self.subTest(exit_code=exit_code, timed_out=timed_out):
                Path(self.history_path).unlink(missing_ok=True)
                result = SimpleNamespace(
                    exit_code=exit_code,
                    stderr=stderr,
                    timed_out=timed_out,
                )
                with (
                    patch.object(admin_app, "run_control", return_value=result, create=True) as runner,
                    patch.object(
                        admin_app,
                        "CONTROL_HISTORY_PATH",
                        self.history_path,
                        create=True,
                    ),
                ):
                    status, body = asgi_request("POST", f"/api/admin/control/{action}")

                self.assertEqual(status, expected_status)
                runner.assert_called_once_with(action)
                records = [
                    json.loads(line)
                    for line in Path(self.history_path).read_text().splitlines()
                ]
                self.assertEqual(len(records), 1)
                record = records[0]
                self.assertEqual(record["action"], action)
                self.assertEqual(record["outcome"], outcome)
                self.assertEqual(record["exit_code"], exit_code)
                self.assertGreaterEqual(record["duration_ms"], 0)
                self.assertEqual(
                    datetime.fromisoformat(record["at"]).tzinfo,
                    timezone.utc,
                )
                if exit_code == 1:
                    payload = json.loads(body)
                    self.assertEqual(record["stderr_tail"], "x" * 500)
                    self.assertIn("x" * 500, payload["detail"])
                    self.assertNotIn("leading-", payload["detail"])

    def test_success_body_reports_the_completed_action(self) -> None:
        result = SimpleNamespace(exit_code=0, stderr="progress output", timed_out=False)
        with (
            patch.object(admin_app, "run_control", return_value=result, create=True),
            patch.object(
                admin_app,
                "CONTROL_HISTORY_PATH",
                self.history_path,
                create=True,
            ),
        ):
            status, body = asgi_request("POST", "/api/admin/control/resume")

        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"ok": True, "action": "resume"})

    def test_history_returns_only_twenty_newest_records_newest_first(self) -> None:
        records = [
            {
                "at": f"2026-07-31T12:{index:02d}:00+00:00",
                "action": "pause",
                "outcome": "ok",
                "exit_code": 0,
                "duration_ms": index,
                "stderr_tail": "",
            }
            for index in range(25)
        ]
        Path(self.history_path).write_text(
            "".join(json.dumps(record) + "\n" for record in records)
        )

        with patch.object(
            admin_app,
            "CONTROL_HISTORY_PATH",
            self.history_path,
            create=True,
        ):
            status, body = asgi_request("GET", "/api/admin/control/history")

        self.assertEqual(status, 200)
        history = json.loads(body)
        self.assertEqual(len(history), 20)
        self.assertEqual(
            [record["duration_ms"] for record in history],
            list(range(24, 4, -1)),
        )

    def test_history_is_empty_when_file_is_missing(self) -> None:
        with patch.object(
            admin_app,
            "CONTROL_HISTORY_PATH",
            self.history_path,
            create=True,
        ):
            status, body = asgi_request("GET", "/api/admin/control/history")

        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), [])


if __name__ == "__main__":
    unittest.main()
