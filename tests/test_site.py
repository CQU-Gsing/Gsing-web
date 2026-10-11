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

    def test_training_poll(self):
        from datetime import datetime
        from src.polls import CHINA_TIME, POLL_ID, POLL_CLOSE
        user = self.store.create_user("poll-tester", "poll@example.test", "test-password")
        before = datetime(2026, 10, 10, 23, 59, 59, tzinfo=CHINA_TIME)
        with self.app.test_client() as client, patch("main.china_now", return_value=before), patch("src.polls.china_now", return_value=before):
            self.assertIn("登录并投票", client.get("/polls/vision-training/").get_data(as_text=True))
            self.assertEqual(client.post("/polls/vision-training/", data={}).status_code, 302)
            with client.session_transaction() as session:
                session.update(user_id=user["id"], username=user["username"], role="user")
                token = session["poll_csrf"]
            url = "/polls/vision-training/"
            self.assertEqual(client.post(url, data={"team_name": "一队", "choices": "1011-am"}).status_code, 400)
            self.assertEqual(client.post(url, data={"csrf_token": token,"choices": []}).status_code, 400)
            self.assertEqual(client.post(url, data={"csrf_token": token,"team_name": "一队", "choices": "bad"}).status_code, 400)
            self.assertEqual(client.post(url, data={"csrf_token": token,"team_name": "一队", "choices": ["1011-am","1012-pm","1011-am"]}).status_code, 302)
            self.assertEqual(len(self.store.get_poll_vote(POLL_ID,user["id"])["choices"]),2)
            self.assertEqual(client.post(url,data={"csrf_token":token,"team_name":"二队","choices":"1017-evening"}).status_code,302)
            vote=self.store.get_poll_vote(POLL_ID,user["id"])
            self.assertEqual(vote["team_name"],"二队")
            self.assertEqual(vote["choices"],["1017-evening"])
            self.assertEqual(self.store.poll_results()["total"],1)
            self.assertEqual(client.post("/polls/vision-freshman-training/",data={"csrf_token":token,"choices":"1011-pm"}).status_code,302)
            self.assertEqual(self.store.get_poll_vote("freshman-training-202610",user["id"])["choices"],["1011-pm"])
            self.assertEqual(self.store.get_poll_vote(POLL_ID,user["id"])["choices"],["1017-evening"])
            self.assertIn('name="team_name"',client.get(url).get_data(as_text=True))
            self.assertNotIn('name="team_name"',client.get("/polls/vision-freshman-training/").get_data(as_text=True))

            self.assertEqual(client.get("/admin/polls/vision-training/").status_code,403)
            self.assertEqual(client.get("/admin/polls/vision-training/export.csv").status_code,403)
            with patch("src.polls.china_now",return_value=POLL_CLOSE), patch("main.china_now",return_value=POLL_CLOSE):
                self.assertEqual(client.post(url,data={"csrf_token":token,"team_name":"三队","choices":"1011-am"}).status_code,400)
                self.assertIn("已截止",client.get(url).get_data(as_text=True))
                self.assertEqual(self.store.get_poll_vote(POLL_ID,user["id"])["choices"],["1017-evening"])
            with client.session_transaction() as session:
                session["role"]="admin"
            self.assertIn("poll-tester",client.get("/admin/polls/vision-training/").get_data(as_text=True))
            import csv, io
            response=client.get("/admin/polls/vision-training/export.csv")
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.data.startswith(b"\xef\xbb\xbf"))
            records=list(csv.reader(io.StringIO(response.data.decode("utf-8-sig"))))
            self.assertEqual(records[1][0],"poll-tester")
            self.assertEqual(len(records[0]),12)
            self.assertEqual(records[1][-1],"是")
            self.assertEqual(response.headers["Cache-Control"],"no-store")
            self.assertNotIn("最近动态管理",client.get("/admin").get_data(as_text=True))
            self.assertIn("Gsing视觉组新生考核培训",client.get("/admin/polls/vision-freshman-training/").get_data(as_text=True))
            freshman_export=client.get("/admin/polls/vision-freshman-training/export.csv")
            self.assertEqual(freshman_export.status_code,200)
            freshman_rows=list(csv.reader(io.StringIO(freshman_export.data.decode("utf-8-sig"))))
            self.assertEqual(freshman_rows[1][3],"是")
            self.assertEqual(client.get("/articles/freshman-training-202610").location,"/polls/vision-freshman-training/")
            self.assertEqual(client.get("/polls/freshman-training/").location,"/polls/vision-freshman-training/")
            self.assertEqual(client.get("/admin/polls/freshman-training/export.csv").location,"/admin/polls/vision-freshman-training/export.csv")


            home=client.get("/").get_data(as_text=True)
            self.assertIn("Gsing视觉组实训培训时间",home)
            self.assertNotIn("下一个赛场",home)
            self.assertEqual(client.get("/articles/"+POLL_ID).location,"/polls/vision-training/")
            for asset in self.main.PAGE_ASSETS:
                with client.get("/assets/"+asset) as response:
                    self.assertEqual(response.status_code,200,asset)
            for private in ["base.html","admin/index.html","../main.py"]:
                self.assertIn(client.get("/assets/"+private).status_code,[403,404])
        self.store.delete_user(user["id"])

    def test_training_resources(self):
        with self.app.test_client() as client:
            self.assertIn("2026 视觉组培训 PPT 课件",client.get("/").get_data(as_text=True))
            response=client.get("/articles/vision-training-resources-20261011")
            self.assertEqual(response.status_code,200)
            html=response.get_data(as_text=True)
            self.assertNotIn("<video",html)
            self.assertNotIn(".mp4",html)
            for name in ["GSing视觉组2026新生培训.pptx", "CRTC视觉组培训_YOLO部署与一键抓取_v1.1.pptx"]:
                url="/media/pages/2026视觉组培训/"+name
                self.assertIn(name,html)
                with client.head(url) as file_response:
                    self.assertEqual(file_response.status_code,200)
                    self.assertGreater(int(file_response.headers["Content-Length"]),0)
                if name.endswith(".mp4"):
                    with client.get(url,headers={"Range":"bytes=0-31"}) as partial:
                        self.assertEqual(partial.status_code,206)
                        self.assertEqual(len(partial.data),32)

    def test_public_roster_fields(self):
        data = json.loads((ROOT / "data/team.json").read_text(encoding="utf-8"))
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
                    self.assertIn("shared/theme.css", html)
                    self.assertEqual(html.count('aria-label="主导航"'), 1)
                    for asset in re.findall(r'(?:src|href)="(/(?:assets|media)/[^"]+)"', html):
                        path = unquote(urlsplit(asset).path).lstrip("/")
                        self.assertTrue((ROOT / ("pages/" + path.removeprefix("assets/") if path.startswith("assets/") else path)).is_file(), path)
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
            for route in ["/data/team-source.md", "/data/team.json", "/pages/main.md", "/docs/private/team-source.md", "/media/../docs/private/team-source.md"]:
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

    def test_resources_skip_access_logs_but_probes_are_logged(self):
        with self.app.test_client() as client, patch.object(self.store, "record_visit") as record, patch.object(self.main, "format_ip_city") as locate, patch.object(self.main.access_logger, "info") as info, patch.object(self.main.access_logger, "warning") as warning:
            for path in ["/assets/shared/theme.css", "/media/missing.png", "/static/missing.css", "/favicon.ico", "/robots.txt"]:
                with client.get(path) as response:
                    self.assertIn(response.status_code, [200, 404])
            record.assert_not_called()
            locate.assert_not_called()
            info.assert_not_called()
            self.assertEqual(client.get("/media/private.key").status_code, 403)
            warning.assert_called_once()
            record.assert_not_called()
            client.get("/login?next=/admin&code=secret")
            self.assertEqual(record.call_args.kwargs["path"], "/login")
            self.assertNotIn("secret", info.call_args.args[0])

    def test_additional_probes_and_unsafe_methods(self):
        with self.app.test_client() as client, patch.object(self.store, "record_visit") as record:
            for path in ["/media/main.py", "/assets/config.yml", "/media/cert.pem", "/.git/config.", "/data./site.db", "/console", "/actuator/env", "/vendor/phpunit", "/web.config"]:
                self.assertEqual(client.get(path).status_code, 403, path)
            for method in ["TRACE", "CONNECT", "TRACK"]:
                self.assertEqual(client.open("/", method=method).status_code, 403)
            self.assertEqual(client.get("/", environ_overrides={"RAW_URI": "/media/%252e%252e/main.py"}).status_code, 403)
            record.assert_not_called()

    def test_team_layout_is_focused(self):
        css = (ROOT / "pages/team/team.css").read_text(encoding="utf-8")
        self.assertIn(".team-roster", css)
        self.assertNotIn(".category-grid", css)
        self.assertNotIn(".hero", css)


if __name__ == "__main__":
    unittest.main()
