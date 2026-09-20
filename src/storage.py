from __future__ import annotations

import sqlite3
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
            """)
            count = db.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            visit_columns = {row[1] for row in db.execute("PRAGMA table_info(visits)").fetchall()}
            if "location" not in visit_columns:
                db.execute("ALTER TABLE visits ADD COLUMN location TEXT NOT NULL DEFAULT ''")
            if count == 0:
                db.executemany("INSERT INTO articles(slug,title,category,summary,content,published) VALUES(?,?,?,?,?,1)", [
                    ("robocon-2026", "向赛场出发：我们的 2026 ROBOCON", "赛事记录", "从方案论证到整机联调，记录 GSing 仿生足式机器人的完整赛季。", "这是一段关于协作、试错与坚持的赛季记录。\n\n机械、硬件、电控和视觉组围绕同一个目标持续迭代，让机器人从图纸走上赛场。"),
                    ("four-legged-robot", "四足机器人：从步态到稳定控制", "技术笔记", "把复杂的运动拆成可以验证的小问题，再一步步还原完整能力。", "四足平台的稳定运动来自结构、驱动、状态估计与控制策略的共同作用。\n\n我们用分阶段测试减少系统耦合带来的不确定性。"),
                    ("team-recruitment", "加入 GSing，一起解码未来", "战队招新", "这里不只招募经验丰富的人，也欢迎愿意学习、动手和一起解决问题的你。", "GSing 面向重庆大学在校同学招募机械、硬件、电控、视觉与宣传运营方向成员。\n\n比起现成答案，我们更看重好奇心、行动力与可靠的协作。"),
                ])

    def initialize_superadmin(self, username: str, password: str):
        with self.connect() as db:
            row = db.execute("SELECT id, role FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
            password_hash = generate_password_hash(password)
            if row:
                db.execute("UPDATE users SET password_hash=?, role='superadmin' WHERE id=?", (password_hash, row["id"]))
            else:
                db.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,'superadmin')", (username, password_hash))

    def authenticate(self, username: str, password: str):
        with self.connect() as db:
            row = db.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
            if row and check_password_hash(row["password_hash"], password):
                db.execute("UPDATE users SET last_login_at=CURRENT_TIMESTAMP WHERE id=?", (row["id"],))
                return dict(row)
        return None

    def create_user(self, username: str, password: str):
        try:
            with self.connect() as db:
                cursor = db.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?, 'user')", (username, generate_password_hash(password)))
                row = db.execute("SELECT id,username,role,created_at,last_login_at FROM users WHERE id=?", (cursor.lastrowid,)).fetchone()
                return dict(row)
        except sqlite3.IntegrityError:
            return None

    def get_user(self, user_id: int):
        with self.connect() as db:
            row = db.execute("SELECT id,username,role,created_at,last_login_at FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None

    def list_users(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT id,username,role,created_at,last_login_at FROM users ORDER BY CASE role WHEN 'superadmin' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END, id").fetchall()]

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

    def create_article(self, *, slug, title, category, summary, content, published):
        unique_slug = slug
        with self.connect() as db:
            index = 2
            while db.execute("SELECT 1 FROM articles WHERE slug = ?", (unique_slug,)).fetchone():
                unique_slug = f"{slug}-{index}"; index += 1
            cursor = db.execute("INSERT INTO articles(slug,title,category,summary,content,published) VALUES(?,?,?,?,?,?)", (unique_slug, title, category, summary, content, int(published)))
            article_id = cursor.lastrowid
        return self.get_article_by_id(article_id)

    def update_article(self, article_id, *, title, category, summary, content, published):
        with self.connect() as db:
            db.execute("UPDATE articles SET title=?,category=?,summary=?,content=?,published=?,updated_at=? WHERE id=?", (title, category, summary, content, int(published), datetime.now().isoformat(timespec="seconds"), article_id))

    def delete_article(self, article_id):
        with self.connect() as db:
            db.execute("DELETE FROM articles WHERE id = ?", (article_id,))

    def record_visit(self, *, ip, location, method, path, status, user_agent, username, elapsed_ms):
        with self.connect() as db:
            db.execute(
                "INSERT INTO visits(ip,location,username,method,path,status,elapsed_ms,user_agent) VALUES(?,?,?,?,?,?,?,?)",
                (ip, location, username, method, path, status, elapsed_ms, user_agent),
            )
