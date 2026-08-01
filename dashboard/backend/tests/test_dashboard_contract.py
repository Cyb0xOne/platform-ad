import asyncio
import importlib
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

_ = os.environ.setdefault(
    "FORCAD_DSN",
    "postgresql://test:test@localhost:5432/forcad_test",
)

dashboard = importlib.import_module("app")
BACKEND = Path(__file__).resolve().parents[1]


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


def call_with_cursor(function: Any, fake: FakeCursor, *args: Any) -> Any:
    with patch.object(dashboard, "cursor", lambda: use_cursor(fake)):
        return function(*args)


def asgi_get(path: str) -> tuple[int, dict[str, str], bytes]:
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
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    asyncio.run(dashboard.app(scope, receive, send))
    start = next(message for message in messages if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    headers = {
        key.decode("latin-1"): value.decode("latin-1")
        for key, value in start["headers"]
    }
    return start["status"], headers, body


class ExistingApiContractTest(unittest.TestCase):
    def test_game_contract(self) -> None:
        row = {
            "real_round": 12,
            "flag_lifetime": 5,
            "round_time": 60,
            "game_running": True,
        }

        self.assertEqual(
            call_with_cursor(dashboard.game, FakeCursor(row)),
            row,
        )

    def test_scoreboard_contract_and_ctftime_formula(self) -> None:
        tasks = [{
            "id": 1,
            "name": "example",
            "checker_type": "service",
            "checker_timeout": 10,
            "puts": 1,
            "gets": 1,
            "places": 1,
            "get_period": 1,
            "default_score": 100.0,
        }]
        rows = [{
            "team_id": 7,
            "team": "Athena",
            "highlighted": True,
            "ip": "10.13.37.11",
            "task_id": 1,
            "status": 101,
            "score": 100.0,
            "stolen": 3,
            "lost": 1,
            "checks": 4,
            "checks_passed": 3,
        }, {
            "team_id": 8,
            "team": "Ares",
            "highlighted": False,
            "ip": "10.13.37.12",
            "task_id": 1,
            "status": 104,
            "score": 80.0,
            "stolen": 1,
            "lost": 2,
            "checks": 0,
            "checks_passed": 0,
        }]

        response = call_with_cursor(
            dashboard.scoreboard,
            FakeCursor(tasks, rows),
        )

        self.assertEqual(response, {
            "tasks": [{**tasks[0], "ports": "10000"}],
            "teams": [{
                "team_id": 8,
                "team": "Ares",
                "highlighted": False,
                "ip": "10.13.37.12",
                "total": 80.0,
                "services": {1: {
                    "status": "DOWN",
                    "score": 80.0,
                    "stolen": 1,
                    "lost": 2,
                    "sla": 100.0,
                }},
                "pos": 1,
            }, {
                "team_id": 7,
                "team": "Athena",
                "highlighted": True,
                "ip": "10.13.37.11",
                "total": 75.0,
                "services": {1: {
                    "status": "UP",
                    "score": 100.0,
                    "stolen": 3,
                    "lost": 1,
                    "sla": 75.0,
                }},
                "pos": 2,
            }],
        })

    def test_attacks_contract_and_limit(self) -> None:
        submitted = datetime(2026, 7, 31, 12, 30, tzinfo=timezone.utc)
        fake = FakeCursor([{
            "submit_time": submitted,
            "attacker": "Ares",
            "victim": "Athena",
            "service": "example",
            "flag_round": 11,
        }])

        response = call_with_cursor(dashboard.attacks, fake, 17)

        self.assertEqual(response, [{
            "submit_time": "2026-07-31T12:30:00+00:00",
            "attacker": "Ares",
            "victim": "Athena",
            "service": "example",
            "flag_round": 11,
        }])
        self.assertEqual(fake.calls[0][1], (17,))

    def test_firstblood_contract(self) -> None:
        first = datetime(2026, 7, 31, 12, 31, tzinfo=timezone.utc)

        response = call_with_cursor(dashboard.firstblood, FakeCursor([{
            "task_id": 1,
            "attacker": "Ares",
            "submit_time": first,
        }]))

        self.assertEqual(response, {
            1: {
                "attacker": "Ares",
                "submit_time": "2026-07-31T12:31:00+00:00",
            },
        })

    def test_timeline_contract(self) -> None:
        response = call_with_cursor(dashboard.timeline, FakeCursor([{
            "round": 12,
            "team_id": 8,
            "team": "Ares",
            "score": 79.96,
        }]))

        self.assertEqual(response, [{
            "round": 12,
            "team_id": 8,
            "team": "Ares",
            "score": 80.0,
        }])

    def test_public_routes_keep_api_docs_without_ssh_writes(self) -> None:
        methods_by_path = {
            getattr(route, "path", ""): getattr(route, "methods", set())
            for route in dashboard.app.routes
        }

        self.assertIn("/api/docs", methods_by_path)
        self.assertNotIn(
            "/api/team/{team_id}/authorized_key",
            methods_by_path,
        )
        self.assertNotIn(
            "/api/team/{team_id}/authorized_keys",
            methods_by_path,
        )


class UiCoexistenceContractTest(unittest.TestCase):
    def test_root_defaults_to_byte_identical_legacy_index(self) -> None:
        expected = (BACKEND / "static/index.html").read_bytes()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DASHBOARD_DEFAULT_UI", None)
            status, headers, body = asgi_get("/")

        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "text/html; charset=utf-8")
        self.assertEqual(body, expected)

    def test_explicit_legacy_index_is_byte_identical(self) -> None:
        status, _, body = asgi_get("/legacy/")

        self.assertEqual(status, 200)
        self.assertEqual(body, (BACKEND / "static/index.html").read_bytes())

    def test_next_returns_controlled_503_when_react_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing-react"
            with patch.object(dashboard, "REACT_FRONTEND", str(missing), create=True):
                status, _, body = asgi_get("/next/")

        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body), {
            "detail": "React dashboard build is unavailable.",
        })

    def test_next_serves_react_index_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            react = Path(temporary)
            react_index = b"<!doctype html><title>React dashboard</title>"
            (react / "index.html").write_bytes(react_index)
            with patch.object(dashboard, "REACT_FRONTEND", str(react), create=True):
                status, _, body = asgi_get("/next/")

        self.assertEqual(status, 200)
        self.assertEqual(body, react_index)

    def test_react_default_switches_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            react = Path(temporary)
            react_index = b"<!doctype html><title>Default React</title>"
            (react / "index.html").write_bytes(react_index)
            with (
                patch.object(dashboard, "REACT_FRONTEND", str(react), create=True),
                patch.dict(os.environ, {"DASHBOARD_DEFAULT_UI": "react"}),
            ):
                status, _, body = asgi_get("/")

        self.assertEqual(status, 200)
        self.assertEqual(body, react_index)

    def test_react_assets_are_served(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            assets = Path(temporary) / "assets"
            assets.mkdir()
            expected = b"console.log('dashboard')"
            (assets / "dashboard.js").write_bytes(expected)
            with self._react_assets_from(assets):
                status, _, body = asgi_get("/assets/dashboard.js")

        self.assertEqual(status, 200)
        self.assertEqual(body, expected)

    def test_react_assets_reject_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets"
            assets.mkdir()
            (root / "secret.txt").write_text("not public")
            with self._react_assets_from(assets):
                status, _, body = asgi_get("/assets/../secret.txt")

        self.assertEqual(status, 404)
        self.assertNotIn(b"not public", body)

    def test_root_legacy_assets_remain_available(self) -> None:
        expected = (BACKEND / "static/cyb0x1_ares.webp").read_bytes()

        status, _, body = asgi_get("/cyb0x1_ares.webp")

        self.assertEqual(status, 200)
        self.assertEqual(body, expected)

    def test_specific_routes_precede_legacy_static_catch_all(self) -> None:
        routes = dashboard.app.routes
        legacy_static = next((
            index for index, route in enumerate(routes)
            if getattr(route, "name", "") == "static"
        ), None)
        if legacy_static is None:
            self.fail("legacy static catch-all is not registered")
        protected = [
            index for index, route in enumerate(routes)
            if getattr(route, "path", "").startswith("/api/")
            or getattr(route, "path", "") in {"/next/", "/legacy/", "/assets"}
        ]

        self.assertTrue(protected)
        self.assertTrue(all(index < legacy_static for index in protected))
        self.assertEqual(legacy_static, len(routes) - 1)

    def _react_assets_from(self, directory: Path):
        route = next((
            route for route in dashboard.app.routes
            if getattr(route, "name", "") == "react-assets"
        ), None)
        if route is None:
            self.fail("React assets route is not registered")
        static_files = route.app
        return patch.multiple(
            static_files,
            directory=str(directory),
            all_directories=[str(directory)],
            config_checked=False,
        )


if __name__ == "__main__":
    unittest.main()
