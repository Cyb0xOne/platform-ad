import importlib
import os
import re
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

_ = os.environ.setdefault(
    "FORCAD_DSN",
    "postgresql://test:test@localhost:5432/forcad_test",
)

public_app = importlib.import_module("app")


class FakeCursor:
    def __init__(self, results: tuple[Any, ...]):
        self.results = list(results)

    def execute(self, *_args: object, **_kwargs: object) -> None:
        pass

    def fetchall(self) -> Any:
        return self.results.pop(0)

    def fetchone(self) -> Any:
        return self.results.pop(0)


@contextmanager
def fake_cursor(*results: Any):
    yield FakeCursor(results)


def service_block(compose: str, service: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(service)}:\n(.*?)(?=^  [\w-]+:|^networks:|\Z)",
        compose,
    )
    if match is None:
        raise AssertionError(f"service {service!r} is not defined")
    return match.group(1)


class Phase0ContractTest(unittest.TestCase):
    def test_public_scoreboard_omits_team_token(self) -> None:
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
        team_rows = [{
            "team_id": 7,
            "team": "Athena",
            "highlighted": True,
            "ip": "10.13.37.11",
            "token": "must-not-leak",
            "task_id": 1,
            "status": 101,
            "score": 100.0,
            "stolen": 0,
            "lost": 0,
            "checks": 1,
            "checks_passed": 1,
        }]
        with patch.object(
            public_app,
            "cursor",
            lambda: fake_cursor(tasks, team_rows),
        ):
            response = public_app.scoreboard()

        self.assertTrue(response["teams"])
        self.assertTrue(all(
            "token" not in team for team in response["teams"]
        ))

    def test_public_listener_does_not_register_admin_routes(self) -> None:
        paths = {
            getattr(route, "path", "") for route in public_app.app.routes
        }

        self.assertFalse(any(
            path.startswith("/api/admin") for path in paths
        ))

    def test_vulnbox_key_routes_are_admin_only(self) -> None:
        admin_app = importlib.import_module("admin_app")
        public_methods = {
            getattr(route, "path", ""): getattr(route, "methods", set())
            for route in public_app.app.routes
        }
        admin_methods = {
            getattr(route, "path", ""): getattr(route, "methods", set())
            for route in admin_app.app.routes
        }

        self.assertNotIn(
            "/api/team/{team_id}/authorized_key",
            public_methods,
        )
        self.assertNotIn(
            "/api/team/{team_id}/authorized_keys",
            public_methods,
        )
        self.assertEqual(
            admin_methods["/api/admin/team/{team_id}/authorized_key"],
            {"POST"},
        )
        self.assertEqual(
            admin_methods["/api/admin/team/{team_id}/authorized_keys"],
            {"GET"},
        )

    def test_public_ui_does_not_render_team_token(self) -> None:
        html = (
            Path(__file__).resolve().parents[1] / "static/index.html"
        ).read_text()

        self.assertNotIn("team.token", html)
        self.assertNotIn("Team token", html)

    def test_admin_listener_exposes_team_token(self) -> None:
        admin_app = importlib.import_module("admin_app")
        route = next(
            (
                route
                for route in admin_app.app.routes
                if getattr(route, "path", "")
                == "/api/admin/team/{team_id}/token"
            ),
            None,
        )
        if route is None:
            self.fail("admin token route is not registered")

        with patch.object(
            admin_app,
            "cursor",
            lambda: fake_cursor({
                "team_id": 7,
                "team": "Athena",
                "token": "admin-only-token",
            }),
        ):
            response = route.endpoint(7)

        self.assertEqual(response, {
            "team_id": 7,
            "team": "Athena",
            "token": "admin-only-token",
        })

    def test_admin_listener_is_bound_to_loopback_only(self) -> None:
        compose_path = Path(os.environ.get(
            "DASHBOARD_COMPOSE_FILE",
            Path(__file__).resolve().parents[2] / "docker-compose.yml",
        ))
        compose = compose_path.read_text()
        public_service = service_block(compose, "dashboard")
        admin_service = service_block(compose, "dashboard-admin")
        admin_ports = [
            line.strip()
            for line in admin_service.splitlines()
            if line.lstrip().startswith("-") and ":8000" in line
        ]

        self.assertNotIn("admin_app:app", public_service)
        self.assertIn("admin_app:app", admin_service)
        self.assertEqual(admin_ports, ['- "127.0.0.1:8091:8000"'])
