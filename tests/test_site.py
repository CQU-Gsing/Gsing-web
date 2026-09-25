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
                self.assertEqual(client.get(route).status_code, 403)

    def test_community_times_are_china_time(self):
        from datetime import datetime, timezone, timedelta
        from src.storage import community_record
        article = self.store.get_article("2026-awards")
        with self.store.connect() as db:
            db.execute("INSERT INTO comments(article_id,username,content,created_at) VALUES(?,?,?,?)",
                       (article["id"], "test", "timezone-check", "2026-12-31 20:15:00"))
            db.execute("INSERT INTO messages(username,content,created_at) VALUES(?,?,?)",
                       ("test", "timezone-check", "2026-12-31 20:15:00"))
        for records in [self.store.list_comments(article["id"]), self.store.list_messages()]:
            record = next(row for row in records if row["content"] == "timezone-check")
            self.assertEqual(record["created_at"], "2027-01-01 04:15:00+08:00")
            self.assertEqual(community_record(record)["created_at"], record["created_at"])
        before = datetime.now(timezone.utc)
        self.store.add_comment(article["id"], None, "test", "new-time-check")
        self.store.add_message(None, "test", "new-time-check")
        after = datetime.now(timezone.utc)
        for records in [self.store.list_comments(), self.store.list_messages()]:
            record = next(row for row in records if row["content"] == "new-time-check")
            timestamp = datetime.fromisoformat(record["created_at"])
            self.assertEqual(timestamp.utcoffset(), timedelta(hours=8))
            self.assertLessEqual(before - timedelta(seconds=1), timestamp)
            self.assertLessEqual(timestamp, after)
        with self.app.test_client() as client:
            for route in ["/articles/2026-awards", "/message-board"]:
                html = client.get(route).get_data(as_text=True)
                self.assertIn("2027-01-01 04:15", html)
                self.assertIn('datetime="2027-01-01T04:15:00+08:00"', html)
                self.assertIn("北京时间", html)

    def test_scan_paths_blocked_without_visit_writes(self):
        paths = ["/.git/config", "/.env", "/.env.local", "/.env.production", "/.env.staging", "/.env.development",
                 "/media/.env", "/STATIC/.GIT/config", "/%252eenv", "/static/%252e%252e/data/site.db",
                 "/media/%5c..%5c.env", "/data/site.db", "/src/storage.py", "/logs/access.log",
                 "/wp-login.php", "/phpmyadmin/", "/.env%00", "/main.py"]
        with self.app.test_client() as client, patch.object(self.store, "record_visit") as record, patch.object(self.main, "format_ip_city") as locate:
            for method in ["GET", "HEAD", "POST"]:
                for path in paths:
                    with self.subTest(path=path, method=method):
                        response = client.open(path, method=method)
                        self.assertEqual(response.status_code, 403)
                        self.assertEqual(response.headers["Cache-Control"], "no-store")
            record.assert_not_called()
            locate.assert_not_called()

    def test_guard_does_not_block_public_paths_or_queries(self):
        from src.request_guard import blocked_path_reason
        for path in ["/", "/admin", "/login", "/register", "/api/email-code", "/message-board",
                     "/media/pages/2026RC/一队_任务赛_三等奖.webp", "/static/css/base.css",
                     "/articles/env-guide", "/.well-known/acme-challenge/token"]:
            self.assertIsNone(blocked_path_reason(path), path)
        with self.app.test_client() as client:
            self.assertEqual(client.get("/?next=/.env").status_code, 200)
            # No IP ban: a legitimate request still works after a blocked probe.
            client.get("/.env")
            self.assertEqual(client.get("/").status_code, 200)

    def test_team_layout_is_focused(self):
        css = (ROOT / "static/css/team.css").read_text(encoding="utf-8")
        self.assertIn(".team-roster", css)
        self.assertNotIn(".category-grid", css)
        self.assertNotIn(".hero", css)


if __name__ == "__main__":
    unittest.main()
