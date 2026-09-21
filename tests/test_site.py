"""Regression checks using a temporary database; never starts a server."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

from src.storage import ArticleStore

ROOT = Path(__file__).resolve().parents[1]


class SiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.connections = []
        class IsolatedStore(ArticleStore):
            def connect(self):
                connection = super().connect()
                cls.connections.append(connection)
                return connection
        cls.store = IsolatedStore(Path(cls.temp.name) / "site.db")
        with patch("src.storage.ArticleStore", return_value=cls.store), patch.object(cls.store, "initialize_superadmin"):
            import main
        cls.app = main.app
        cls.app.config.update(TESTING=True)
        cls.main = main

    @classmethod
    def tearDownClass(cls):
        for connection in cls.connections:
            connection.close()
        cls.temp.cleanup()

    def test_public_roster_fields(self):
        data = json.loads((ROOT / "content/team.json").read_text(encoding="utf-8"))
        members = [member for season in data["seasons"] for member in season["members"]]
        self.assertEqual(len(members), 37)
        for member in members:
            self.assertEqual(set(member), {"name", "role", "college", "major", "grade"})
            self.assertTrue(member["major"])
            self.assertRegex(member["grade"], r"^20\d{2}级$")
            if member["name"] == "黄益鹏":
                self.assertEqual(member["role"], "视觉组成员")
        raw = json.dumps(data, ensure_ascii=False)
        self.assertNotRegex(raw, r"\b1[3-9]\d{9}\b|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")

    def test_all_pages_and_assets(self):
        routes = ["/", "/login", "/register", "/message-board", "/projects/gsing/", "/awards/2026/", "/articles/2026-awards"]
        routes += ["/groups/" + group["slug"] + "/" for group in self.main.TEAM_CONTENT["groups"]]
        with self.app.test_client() as client:
            for route in routes:
                with self.subTest(route=route):
                    response = client.get(route)
                    self.assertEqual(response.status_code, 200)
                    html = response.get_data(as_text=True)
                    self.assertIn("css/theme.css", html)
                    self.assertEqual(html.count('aria-label="主导航"'), 1)
                    for asset in re.findall(r'(?:src|href)="(/(?:static|media)/[^"]+)"', html):
                        path = unquote(urlsplit(asset).path).lstrip("/")
                        self.assertTrue((ROOT / path).is_file(), path)
            history = client.get("/projects/gsing/").get_data(as_text=True)
            self.assertIn('<th scope="col">专业</th>', history)
            self.assertEqual(history.count('<th scope="row">'), 37)
            with client.session_transaction() as session:
                session.update(user_id=1, username="test", role="superadmin")
            article = self.store.get_article("2027-recruitment")
            for route in ["/admin", "/admin/articles/new", "/admin/articles/" + str(article["id"]) + "/edit", "/admin/pages/gsing"]:
                self.assertEqual(client.get(route).status_code, 200, route)

    def test_private_sources_not_served(self):
        with self.app.test_client() as client:
            for route in ["/pages/main.md", "/docs/private/team-source.md", "/media/../docs/private/team-source.md"]:
                self.assertEqual(client.get(route).status_code, 404)

    def test_team_layout_is_focused(self):
        css = (ROOT / "static/css/team.css").read_text(encoding="utf-8")
        self.assertIn(".team-roster", css)
        self.assertNotIn(".category-grid", css)
        self.assertNotIn(".hero", css)


if __name__ == "__main__":
    unittest.main()
