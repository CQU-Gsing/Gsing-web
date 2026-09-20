from __future__ import annotations

import os
import re
import logging
import sys
import time
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, abort, flash, g, redirect, render_template, request, send_from_directory, session, url_for

from src.storage import ArticleStore
from src.ip_location import format_ip_location

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
STARTED_AT = datetime.now()
ACCESS_LOG_PATH = LOG_DIR / f"access-{STARTED_AT:%Y%m%d-%H%M%S}.log"


def build_access_logger():
    logger = logging.getLogger("gsing.access")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        formatter = logging.Formatter("%(message)s")
        file_handler = logging.FileHandler(ACCESS_LOG_PATH, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    return logger


access_logger = build_access_logger()
app = Flask(__name__, static_folder="static", template_folder="pages")
app.config.update(
    SECRET_KEY=os.environ.get("GSING_SECRET_KEY", "dev-change-this-secret-before-deploy"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)
store = ArticleStore(BASE_DIR / "data" / "site.db")
store.initialize_superadmin(
    os.environ.get("GSING_ADMIN_USERNAME", "admin"),
    os.environ.get("GSING_ADMIN_PASSWORD", "gsing2024"),
)


def real_client_ip():
    return (
        request.headers.get("CF-Connecting-IP")
        or request.headers.get("X-Real-IP")
        or request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
        or request.remote_addr
        or "unknown"
    )


@app.before_request
def start_request_timer():
    g.request_started_at = time.perf_counter()


@app.after_request
def log_access(response):
    if request.path.startswith(("/static/", "/media/")) or request.path == "/favicon.ico":
        return response
    elapsed_ms = (time.perf_counter() - getattr(g, "request_started_at", time.perf_counter())) * 1000
    ip = real_client_ip().replace("\n", "").replace("\r", "")[:64]
    location = format_ip_location(ip)
    user_agent = request.user_agent.string.replace("\n", " ").replace("\r", " ")[:120]
    username = session.get("username") or "游客"
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {username} [{ip} · {location}] | {request.method} {request.full_path.rstrip('?')} | {response.status_code} | {elapsed_ms:.1f}ms | {user_agent or '-'}"
    access_logger.info(line)
    print(line, file=sys.stdout, flush=True)
    try:
        store.record_visit(ip=ip, location=location, method=request.method, path=request.full_path.rstrip("?"), status=response.status_code, user_agent=user_agent, username=username, elapsed_ms=elapsed_ms)
    except Exception:
        access_logger.exception("保存访问记录失败")
        print(f"保存访问记录失败，详情见 {ACCESS_LOG_PATH}", file=sys.stdout, flush=True)
    return response


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        if session.get("role") not in {"admin", "superadmin"}:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def superadmin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        if session.get("role") != "superadmin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_globals():
    return {"current_user": session.get("username"), "is_admin": session.get("role") in {"admin", "superadmin"}, "is_superadmin": session.get("role") == "superadmin", "admin_name": session.get("username")}


@app.get("/")
def home():
    return render_template("home/index.html", articles=store.list_articles(published_only=True, limit=8))


@app.get("/media/<path:filename>")
def media_file(filename):
    return send_from_directory(BASE_DIR / "media", filename)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = store.authenticate(username, password)
        if user:
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            target = request.args.get("next")
            return redirect(target if target and target.startswith("/") and not target.startswith("//") else (url_for("admin") if user["role"] in {"admin", "superadmin"} else url_for("home")))
        flash("用户名或密码错误", "error")
    return render_template("login/index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not re.fullmatch(r"[A-Za-z0-9_\u4e00-\u9fff]{2,24}", username):
            flash("用户名需为 2–24 位中文、字母、数字或下划线", "error")
        elif len(password) < 8:
            flash("密码至少需要 8 位", "error")
        elif password != confirm:
            flash("两次输入的密码不一致", "error")
        else:
            user = store.create_user(username, password)
            if user:
                session.clear(); session["user_id"] = user["id"]; session["username"] = user["username"]; session["role"] = user["role"]
                flash("注册成功", "success")
                return redirect(url_for("home"))
            flash("用户名已存在", "error")
    return render_template("login/register.html")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.get("/articles/<slug>")
def article(slug: str):
    item = store.get_article(slug)
    if not item or (not item["published"] and session.get("role") not in {"admin", "superadmin"}):
        abort(404)
    return render_template("articles/detail.html", article=item)


@app.get("/admin")
@admin_required
def admin():
    return render_template("admin/index.html", articles=store.list_articles(), users=store.list_users() if session.get("role") == "superadmin" else [])


@app.post("/admin/users/<int:user_id>/role")
@superadmin_required
def set_user_role(user_id: int):
    role = request.form.get("role", "user")
    flash("用户权限已更新" if store.set_user_role(user_id, role) else "无法修改该账户", "success" if role in {"user", "admin"} else "error")
    return redirect(url_for("admin") + "#users")


@app.post("/admin/users/<int:user_id>/delete")
@superadmin_required
def delete_user(user_id: int):
    flash("用户已删除" if store.delete_user(user_id) else "无法删除该账户", "success")
    return redirect(url_for("admin") + "#users")


def slugify(title: str) -> str:
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", title.lower()).strip("-")
    return value or "article"


@app.route("/admin/articles/new", methods=["GET", "POST"])
@admin_required
def new_article():
    if request.method == "POST":
        data = {key: request.form.get(key, "").strip() for key in ("title", "category", "summary", "content")}
        if len(data["title"]) < 2 or len(data["summary"]) < 10 or len(data["content"]) < 20:
            flash("标题、摘要或正文内容过短", "error")
            return render_template("admin/editor.html", article=data, mode="new")
        item = store.create_article(**data, slug=slugify(data["title"]), published=request.form.get("published") == "on")
        flash("文章已发布", "success")
        return redirect(url_for("article", slug=item["slug"]))
    return render_template("admin/editor.html", article={}, mode="new")


@app.route("/admin/articles/<int:article_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_article(article_id: int):
    item = store.get_article_by_id(article_id)
    if not item:
        abort(404)
    if request.method == "POST":
        data = {key: request.form.get(key, "").strip() for key in ("title", "category", "summary", "content")}
        if len(data["title"]) < 2 or len(data["summary"]) < 10 or len(data["content"]) < 20:
            flash("标题、摘要或正文内容过短", "error")
            return render_template("admin/editor.html", article={**item, **data}, mode="edit")
        store.update_article(article_id, **data, published=request.form.get("published") == "on")
        flash("文章已更新", "success")
        return redirect(url_for("admin"))
    return render_template("admin/editor.html", article=item, mode="edit")


@app.post("/admin/articles/<int:article_id>/delete")
@admin_required
def delete_article(article_id: int):
    store.delete_article(article_id)
    flash("文章已删除", "success")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    print("=" * 72)
    print("GSing 网站已启动：http://127.0.0.1:2024")
    print("访问日志：时间 用户 [真实IP] | 方法 路径 | 状态 | 耗时 | 浏览器")
    print(f"本次启动：{STARTED_AT:%Y-%m-%d %H:%M:%S}")
    print(f"日志文件：{ACCESS_LOG_PATH}")
    print("=" * 72)
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "2024")), debug=os.environ.get("FLASK_DEBUG") == "1")
