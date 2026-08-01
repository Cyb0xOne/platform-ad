import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

_ = os.environ.setdefault(
    "FORCAD_DSN",
    "postgresql://test:test@localhost:5432/forcad_test",
)

public_app = importlib.import_module("app")
admin_app = importlib.import_module("admin_app")
BACKEND = Path(__file__).resolve().parents[1]


class UiRouteIsolationTest(unittest.TestCase):
    def test_apps_register_only_their_listener_routes(self) -> None:
        public_paths = {
            getattr(route, "path", "") for route in public_app.app.routes
        }
        admin_paths = {
            getattr(route, "path", "") for route in admin_app.app.routes
        }

        self.assertTrue({"/next/", "/legacy/", "/assets"} <= public_paths)
        self.assertNotIn("/admin/", public_paths)
        self.assertFalse(any(
            path.startswith("/api/admin/") for path in public_paths
        ))

        self.assertTrue({"/admin/", "/assets"} <= admin_paths)
        self.assertNotIn("/next/", admin_paths)
        self.assertNotIn("/legacy/", admin_paths)
        self.assertTrue(all(
            not path.startswith("/api/") or path.startswith("/api/admin/")
            for path in admin_paths
        ))

        admin_routes = admin_app.app.routes
        assets_index = next(
            index for index, route in enumerate(admin_routes)
            if getattr(route, "path", "") == "/assets"
        )
        api_indexes = [
            index for index, route in enumerate(admin_routes)
            if getattr(route, "path", "").startswith("/api/admin/")
        ]
        self.assertTrue(api_indexes)
        self.assertTrue(all(index < assets_index for index in api_indexes))

    def test_apps_share_the_bundled_frontend_layout(self) -> None:
        react_root = BACKEND / "react"
        assets = react_root / "assets"

        self.assertEqual(Path(public_app.REACT_FRONTEND), react_root)
        self.assertEqual(Path(admin_app.REACT_FRONTEND), react_root)
        for module in (public_app, admin_app):
            route = next(
                route for route in module.app.routes
                if getattr(route, "path", "") == "/assets"
            )
            self.assertEqual(Path(route.app.directory), assets)

        with tempfile.TemporaryDirectory() as temporary:
            built = Path(temporary)
            (built / "admin").mkdir()
            (built / "index.html").write_text("public")
            (built / "admin/index.html").write_text("admin")
            with (
                patch.object(public_app, "REACT_FRONTEND", str(built)),
                patch.object(admin_app, "REACT_FRONTEND", str(built)),
            ):
                public_response = public_app.react_index()
                admin_response = admin_app.admin_index()

        self.assertEqual(Path(public_response.path), built / "index.html")
        self.assertEqual(Path(admin_response.path), built / "admin/index.html")

    def test_admin_index_returns_controlled_503_when_build_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing-react"
            with (
                patch.object(admin_app, "REACT_FRONTEND", str(missing)),
                self.assertRaises(HTTPException) as raised,
            ):
                admin_app.admin_index()

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(
            raised.exception.detail,
            "Admin dashboard build is unavailable.",
        )


if __name__ == "__main__":
    unittest.main()
