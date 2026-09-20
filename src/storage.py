from __future__ import annotations

import sqlite3
import secrets
import time
from datetime import datetime
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash


class ArticleStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _init_schema(self):
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    email TEXT UNIQUE COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin','superadmin')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_login_at TEXT
                );
                CREATE TABLE IF NOT EXISTS articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '战队动态',
                    summary TEXT NOT NULL,
                    content TEXT NOT NULL,
                    published INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS page_settings (
                    page_key TEXT PRIMARY KEY,
                    external_url TEXT NOT NULL DEFAULT '',
                    external_label TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    username TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    username TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_articles_published_created
                ON articles(published, created_at DESC);
                CREATE TABLE IF NOT EXISTS visits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    visited_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    ip TEXT NOT NULL,
                    location TEXT NOT NULL DEFAULT '',
                    username TEXT NOT NULL DEFAULT '游客',
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    status INTEGER NOT NULL,
                    elapsed_ms REAL NOT NULL,
                    user_agent TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_visits_ip_time
                ON visits(ip, visited_at DESC);
                CREATE TABLE IF NOT EXISTS site_stats (
                    name TEXT PRIMARY KEY,
                    value INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS email_codes (
                    email TEXT NOT NULL COLLATE NOCASE,
                    purpose TEXT NOT NULL,
                    code TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    sent_at INTEGER NOT NULL,
                    PRIMARY KEY(email, purpose)
                );
            """)
            count = db.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            visit_columns = {row[1] for row in db.execute("PRAGMA table_info(visits)").fetchall()}
            if "location" not in visit_columns:
                db.execute("ALTER TABLE visits ADD COLUMN location TEXT NOT NULL DEFAULT ''")
            db.execute("INSERT OR IGNORE INTO site_stats(name,value) SELECT 'visit_count', COUNT(*) FROM visits")
            user_columns = {row[1] for row in db.execute("PRAGMA table_info(users)").fetchall()}
            if "email" not in user_columns:
                db.execute("ALTER TABLE users ADD COLUMN email TEXT COLLATE NOCASE")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL")
            article_columns = {row[1] for row in db.execute("PRAGMA table_info(articles)").fetchall()}
            if "external_url" not in article_columns:
                db.execute("ALTER TABLE articles ADD COLUMN external_url TEXT NOT NULL DEFAULT ''")
            if "external_label" not in article_columns:
                db.execute("ALTER TABLE articles ADD COLUMN external_label TEXT NOT NULL DEFAULT ''")
            page_columns = {row[1] for row in db.execute("PRAGMA table_info(page_settings)").fetchall()}
            if "content" not in page_columns:
                db.execute("ALTER TABLE page_settings ADD COLUMN content TEXT NOT NULL DEFAULT ''")
            db.execute("INSERT OR IGNORE INTO page_settings(page_key,external_url,external_label) VALUES('gsing','','联系我们')")
            if count == 0:
                db.executemany("INSERT INTO articles(slug,title,category,summary,content,published) VALUES(?,?,?,?,?,1)", [
                    ("2026-awards", "2026 获奖情况", "团队荣誉", "第二十五届 ROBOCON：重庆大学仿生足式机器人挑战赛 1 队获得障碍赛一等奖、任务赛三等奖，2 队获得障碍赛二等奖、任务赛三等奖。", "第二十五届 ROBOCON · 团队荣誉\n重庆大学仿生足式机器人挑战赛 1 队获得障碍赛一等奖、任务赛三等奖。\n重庆大学仿生足式机器人挑战赛 2 队获得障碍赛二等奖、任务赛三等奖。四份团队证书，记录共同完成的这一程。"),
                ])

    def initialize_superadmin(self, username: str, password: str):
        with self.connect() as db:
            row = db.execute("SELECT id, role FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
            password_hash = generate_password_hash(password)
            if row:
                db.execute("UPDATE users SET password_hash=?, role='superadmin', email=COALESCE(email, 'admin@cqu-gsing.tech') WHERE id=?", (password_hash, row["id"]))
            else:
                db.execute("INSERT INTO users(username,email,password_hash,role) VALUES(?,'admin@cqu-gsing.tech',?,'superadmin')", (username, password_hash))

    def authenticate(self, username: str, password: str):
        with self.connect() as db:
            row = db.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE", (username, username)).fetchone()
            if row and check_password_hash(row["password_hash"], password):
                db.execute("UPDATE users SET last_login_at=CURRENT_TIMESTAMP WHERE id=?", (row["id"],))
                return dict(row)
        return None

    def authenticate_by_email(self, email: str):
        with self.connect() as db:
            row = db.execute("SELECT * FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone()
            if row:
                db.execute("UPDATE users SET last_login_at=CURRENT_TIMESTAMP WHERE id=?", (row["id"],))
                return dict(row)
        return None

    def create_user(self, username: str, email: str, password: str):
        try:
            with self.connect() as db:
                cursor = db.execute("INSERT INTO users(username,email,password_hash,role) VALUES(?,?,?, 'user')", (username, email, generate_password_hash(password)))
                row = db.execute("SELECT id,username,email,role,created_at,last_login_at FROM users WHERE id=?", (cursor.lastrowid,)).fetchone()
                return dict(row)
        except sqlite3.IntegrityError:
            return None

    def get_user(self, user_id: int):
        with self.connect() as db:
            row = db.execute("SELECT id,username,email,role,created_at,last_login_at FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None

    def list_users(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT id,username,email,role,created_at,last_login_at FROM users ORDER BY CASE role WHEN 'superadmin' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END, id").fetchall()]

    def email_exists(self, email: str):
        with self.connect() as db:
            return db.execute("SELECT 1 FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone() is not None

    def create_email_code(self, email: str, purpose: str):
        now = int(time.time())
        with self.connect() as db:
            previous = db.execute("SELECT sent_at FROM email_codes WHERE email=? AND purpose=?", (email, purpose)).fetchone()
            if previous and now - previous[0] < 60:
                return None, 60 - (now - previous[0])
            code = f"{secrets.randbelow(1_000_000):06d}"
            db.execute("INSERT INTO email_codes(email,purpose,code,expires_at,sent_at) VALUES(?,?,?,?,?) ON CONFLICT(email,purpose) DO UPDATE SET code=excluded.code,expires_at=excluded.expires_at,sent_at=excluded.sent_at", (email, purpose, code, now + 300, now))
            return code, 0

    def verify_email_code(self, email: str, purpose: str, code: str):
        now = int(time.time())
        with self.connect() as db:
            row = db.execute("SELECT code,expires_at FROM email_codes WHERE email=? AND purpose=?", (email, purpose)).fetchone()
            if not row or row[0] != code or row[1] < now:
                return False
            db.execute("DELETE FROM email_codes WHERE email=? AND purpose=?", (email, purpose))
            return True

    def set_user_role(self, user_id: int, role: str):
        if role not in {"user", "admin"}:
            return False
        with self.connect() as db:
            cursor = db.execute("UPDATE users SET role=? WHERE id=? AND role!='superadmin'", (role, user_id))
            return cursor.rowcount > 0

    def delete_user(self, user_id: int):
        with self.connect() as db:
            cursor = db.execute("DELETE FROM users WHERE id=? AND role!='superadmin'", (user_id,))
            return cursor.rowcount > 0

    def list_articles(self, published_only=False, limit=None):
        sql = "SELECT * FROM articles"
        params = []
        if published_only:
            sql += " WHERE published = 1"
        sql += " ORDER BY created_at DESC, id DESC"
        if limit:
            sql += " LIMIT ?"; params.append(limit)
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, params).fetchall()]

    def get_article(self, slug: str):
        with self.connect() as db:
            row = db.execute("SELECT * FROM articles WHERE slug = ?", (slug,)).fetchone()
        return dict(row) if row else None

    def get_article_by_id(self, article_id: int):
        with self.connect() as db:
            row = db.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        return dict(row) if row else None

    def create_article(self, *, slug, title, category, summary, content, published, external_url="", external_label=""):
        unique_slug = slug
        with self.connect() as db:
            index = 2
            while db.execute("SELECT 1 FROM articles WHERE slug = ?", (unique_slug,)).fetchone():
                unique_slug = f"{slug}-{index}"; index += 1
            cursor = db.execute("INSERT INTO articles(slug,title,category,summary,content,published,external_url,external_label) VALUES(?,?,?,?,?,?,?,?)", (unique_slug, title, category, summary, content, int(published), external_url, external_label))
            article_id = cursor.lastrowid
        return self.get_article_by_id(article_id)

    def update_article(self, article_id, *, title, category, summary, content, published, external_url="", external_label=""):
        with self.connect() as db:
            db.execute("UPDATE articles SET title=?,category=?,summary=?,content=?,published=?,external_url=?,external_label=?,updated_at=? WHERE id=?", (title, category, summary, content, int(published), external_url, external_label, datetime.now().isoformat(timespec="seconds"), article_id))

    def get_page_settings(self, page_key):
        with self.connect() as db:
            row = db.execute("SELECT * FROM page_settings WHERE page_key=?", (page_key,)).fetchone()
        return dict(row) if row else {"page_key": page_key, "external_url": "", "external_label": "", "content": ""}

    def update_page_settings(self, page_key, external_url, external_label, content=""):
        with self.connect() as db:
            db.execute("INSERT INTO page_settings(page_key,external_url,external_label,content) VALUES(?,?,?,?) ON CONFLICT(page_key) DO UPDATE SET external_url=excluded.external_url,external_label=excluded.external_label,content=excluded.content", (page_key, external_url, external_label, content))

    def list_comments(self, article_id=None):
        sql = "SELECT * FROM comments"
        params = ()
        if article_id is not None:
            sql += " WHERE article_id=?"; params = (article_id,)
        sql += " ORDER BY created_at DESC,id DESC"
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, params).fetchall()]

    def add_comment(self, article_id, user_id, username, content):
        with self.connect() as db:
            db.execute("INSERT INTO comments(article_id,user_id,username,content) VALUES(?,?,?,?)", (article_id, user_id, username, content))

    def delete_comment(self, comment_id):
        with self.connect() as db:
            db.execute("DELETE FROM comments WHERE id=?", (comment_id,))

    def list_messages(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM messages ORDER BY created_at DESC,id DESC").fetchall()]

    def add_message(self, user_id, username, content):
        with self.connect() as db:
            db.execute("INSERT INTO messages(user_id,username,content) VALUES(?,?,?)", (user_id, username, content))

    def delete_message(self, message_id):
        with self.connect() as db:
            db.execute("DELETE FROM messages WHERE id=?", (message_id,))

    def toggle_article_published(self, article_id):
        with self.connect() as db:
            cursor = db.execute("UPDATE articles SET published=CASE published WHEN 1 THEN 0 ELSE 1 END,updated_at=? WHERE id=?", (datetime.now().isoformat(timespec="seconds"), article_id))
            return cursor.rowcount > 0

    def delete_article(self, article_id):
        with self.connect() as db:
            db.execute("DELETE FROM articles WHERE id = ?", (article_id,))

    def record_visit(self, *, ip, location, method, path, status, user_agent, username, elapsed_ms):
        with self.connect() as db:
            db.execute(
                "INSERT INTO visits(ip,location,username,method,path,status,elapsed_ms,user_agent) VALUES(?,?,?,?,?,?,?,?)",
                (ip, location, username, method, path, status, elapsed_ms, user_agent),
            )
            db.execute("UPDATE site_stats SET value=value+1 WHERE name='visit_count'")
            return db.execute("SELECT value FROM site_stats WHERE name='visit_count'").fetchone()[0]

    def get_visit_count(self):
        with self.connect() as db:
            row = db.execute("SELECT value FROM site_stats WHERE name='visit_count'").fetchone()
        return row[0] if row else 0
