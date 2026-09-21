from __future__ import annotations

import os
import json
import re
import logging
import sys
import time
import uuid
from datetime import datetime
from functools import wraps
from urllib.parse import urlsplit
from pathlib import Path

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, send_from_directory, session, url_for

from src.storage import ArticleStore
from src.ip_location import format_ip_city
from src.mail_service import send_verify_code

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
TEAM_CONTENT = json.loads((BASE_DIR / "content" / "team.json").read_text(encoding="utf-8"))
AWARD_GALLERY = [
    {"label": "一队 · 障碍赛一等奖", "preview": "/media/pages/2026RC/一队_障碍赛_一等奖.webp"},
    {"label": "一队 · 任务赛三等奖", "preview": "/media/pages/2026RC/一队_任务赛_三等奖.webp"},
    {"label": "二队 · 障碍赛二等奖", "preview": "/media/pages/2026RC/二队_障碍赛_二等奖.webp"},
    {"label": "二队 · 任务赛三等奖", "preview": "/media/pages/2026RC/二队_任务赛_三等奖.webp"},
]
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
    MAX_CONTENT_LENGTH=1024 * 1024 * 1024,
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


def masked_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if not domain:
        return "无效邮箱"
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}***@{domain}"


ALLOWED_MEDIA_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".mp4", ".webm", ".mov"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov"}


def valid_external_url(value: str) -> bool:
    return not value or bool(re.match(r"^(https?://|weixin://)", value, re.IGNORECASE))


def valid_direct_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return parsed.scheme.lower() in {"http", "https"} and bool(parsed.hostname) and not any(char.isspace() or ord(char) < 32 for char in value) and "\\" not in value
    except ValueError:
        return False


def uploaded_media():
    upload_dir = BASE_DIR / "media" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return [{"name": path.name, "url": f"/media/uploads/{path.name}", "kind": "video" if path.suffix.lower() in VIDEO_EXTENSIONS else "image", "size": path.stat().st_size} for path in sorted(upload_dir.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True) if path.is_file() and path.suffix.lower() in ALLOWED_MEDIA_EXTENSIONS]


def article_content_blocks(content: str):
    blocks = []
    pattern = re.compile(r"^\[\[(image|video):([^\]]+)\]\]$")
    link_pattern = re.compile(r"^\[\[link:([^|\]]+)\|([^\]]+)\]\]$")
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        match = pattern.match(line)
        if match and match.group(2).startswith("/media/"):
            blocks.append({"type": match.group(1), "url": match.group(2)})
        elif (link_match := link_pattern.match(line)) and (link_match.group(1).startswith("/media/") or valid_external_url(link_match.group(1))):
            blocks.append({"type": "link", "url": link_match.group(1), "label": link_match.group(2)})
        else:
            blocks.append({"type": "text", "text": line})
    return blocks


@app.before_request
def start_request_timer():
    g.request_started_at = time.perf_counter()


@app.after_request
def log_access(response):
    elapsed_ms = (time.perf_counter() - getattr(g, "request_started_at", time.perf_counter())) * 1000
    ip = real_client_ip().replace("\n", "").replace("\r", "")[:64]
    location = format_ip_city(ip)
    user_agent = request.user_agent.string.replace("\n", " ").replace("\r", " ")[:120]
    username = session.get("username") or "游客"
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    path = request.full_path.rstrip("?")
    if request.path == "/":
        request_icon = "🏠"
    elif request.path.startswith(("/static/", "/media/")):
        request_icon = "📡"
    elif request.path.startswith(("/login", "/register", "/logout")):
        request_icon = "🔐"
    elif request.path.startswith("/admin"):
        request_icon = "🛠️"
    else:
        request_icon = "📁"
    try:
        visit_count = store.record_visit(ip=ip, location=location, method=request.method, path=path, status=response.status_code, user_agent=user_agent, username=username, elapsed_ms=elapsed_ms)
    except Exception:
        access_logger.exception("保存访问记录失败")
        print(f"保存访问记录失败，详情见 {ACCESS_LOG_PATH}", file=sys.stdout, flush=True)
        visit_count = store.get_visit_count()
    line = f"{timestamp} {request_icon} 👤 {username} [{ip}] [{location}] | {request.method} {path} | {response.status_code} | {elapsed_ms:.1f}ms | 👁️ {visit_count}"
    access_logger.info(line)
    print(line, file=sys.stdout, flush=True)
    return response


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def sign_in_user(user):
    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["email"] = user.get("email")
    session["role"] = user["role"]


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
    return {"team_content": TEAM_CONTENT, "current_user": session.get("username"), "is_admin": session.get("role") in {"admin", "superadmin"}, "is_superadmin": session.get("role") == "superadmin", "admin_name": session.get("username"), "visit_count": store.get_visit_count()}


@app.get("/")
def home():
    return render_template("home/index.html", articles=store.list_articles(published_only=True, limit=8))


@app.get("/projects/gsing/")
def gsing_project():
    project = store.get_page_settings("gsing")
    return render_template("team/history.html", project=project, project_blocks=article_content_blocks(project.get("content", "")))


@app.get("/groups/<slug>/")
def team_group(slug: str):
    group = next((item for item in TEAM_CONTENT["groups"] if item["slug"] == slug), None)
    if group is None:
        abort(404)
    return render_template("groups/detail.html", group=group)


@app.get("/pages/home/")
def legacy_home():
    return redirect(url_for("home"), code=301)


@app.get("/pages/devlog/")
def legacy_devlog():
    return redirect(url_for("home") + "#stories", code=301)


@app.get("/media/<path:filename>")
def media_file(filename):
    return send_from_directory(BASE_DIR / "media", filename, mimetype="image/webp" if Path(filename).suffix.lower() == ".webp" else None)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = store.authenticate(username, password)
        if user:
            sign_in_user(user)
            target = request.args.get("next")
            return redirect(target if target and target.startswith("/") and not target.startswith("//") else (url_for("admin") if user["role"] in {"admin", "superadmin"} else url_for("home")))
        flash("用户名或密码错误", "error")
    return render_template("login/index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        code = request.form.get("code", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not re.fullmatch(r"[A-Za-z0-9_\u4e00-\u9fff]{2,24}", username):
            flash("用户名需为 2–24 位中文、字母、数字或下划线", "error")
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash("请输入有效的邮箱地址", "error")
        elif len(password) < 8:
            flash("密码至少需要 8 位", "error")
        elif password != confirm:
            flash("两次输入的密码不一致", "error")
        elif not store.verify_email_code(email, "register", code):
            flash("邮箱验证码错误或已过期", "error")
        else:
            user = store.create_user(username, email, password)
            if user:
                sign_in_user(user)
                flash("注册成功", "success")
                return redirect(url_for("home"))
            flash("用户名已存在", "error")
    return render_template("login/register.html")


@app.post("/api/email-code")
def email_code():
    mail_started_at = time.perf_counter()
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    purpose = str(data.get("purpose", ""))
    if purpose not in {"register", "login"} or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"ok": False, "message": "邮箱地址无效"}), 400
    exists = store.email_exists(email)
    if purpose == "register" and exists:
        return jsonify({"ok": False, "message": "该邮箱已注册，请直接登录"}), 400
    if purpose == "login" and not exists:
        return jsonify({"ok": False, "message": "该邮箱尚未注册"}), 400
    code, wait = store.create_email_code(email, purpose)
    if not code:
        return jsonify({"ok": False, "message": f"请等待 {wait} 秒后重试"}), 429
    success, message = send_verify_code(email, code, purpose)
    mail_elapsed_ms = (time.perf_counter() - mail_started_at) * 1000
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    action = "注册" if purpose == "register" else "登录"
    result = "发送成功" if success else "发送失败"
    line = f"{timestamp} 📧 {action}验证码 [{masked_email(email)}] | {result} | {mail_elapsed_ms:.1f}ms"
    access_logger.info(line)
    print(line, file=sys.stdout, flush=True)
    return jsonify({"ok": success, "message": message}), (200 if success else 503)


@app.route("/login/code", methods=["GET", "POST"])
def login_code():
    if request.method == "GET":
        target = request.args.get("next")
        return redirect(url_for("login", mode="code", **({"next": target} if target else {})))
    email = request.form.get("email", "").strip().lower()
    code = request.form.get("code", "").strip()
    if not store.verify_email_code(email, "login", code):
        flash("邮箱验证码错误或已过期", "error")
        return redirect(url_for("login", mode="code"))
    user = store.authenticate_by_email(email)
    if not user:
        flash("该邮箱尚未注册", "error")
        return redirect(url_for("login", mode="code"))
    sign_in_user(user)
    flash("登录成功", "success")
    target = request.args.get("next")
    if target and target.startswith("/") and not target.startswith("//"):
        return redirect(target)
    return redirect(url_for("admin") if user["role"] in {"admin", "superadmin"} else url_for("home"))


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.get("/awards/2026/")
def awards_2026():
    return render_template("articles/awards.html", award_gallery=AWARD_GALLERY)


@app.get("/articles/<slug>")
def article(slug: str):
    item = store.get_article(slug)
    if not item or (not item["published"] and session.get("role") not in {"admin", "superadmin"}):
        abort(404)
    if item.get("direct_link"):
        if not valid_direct_url(item["external_url"]):
            abort(404)
        return redirect(item["external_url"])
    award_gallery = []
    if item["slug"] == "2026-awards":
        award_gallery = AWARD_GALLERY
    return render_template("articles/detail.html", article=item, content_blocks=article_content_blocks(item["content"]), award_gallery=award_gallery, comments=store.list_comments(item["id"]))


@app.post("/articles/<int:article_id>/comments")
@login_required
def add_article_comment(article_id: int):
    if not store.get_article_by_id(article_id):
        abort(404)
    content = request.form.get("content", "").strip()
    if not 1 <= len(content) <= 1000:
        flash("评论内容需为 1–1000 个字符", "error")
    else:
        store.add_comment(article_id, session["user_id"], session["username"], content)
        flash("评论已发布", "success")
    target = request.form.get("return_to", "/")
    return redirect(target if target.startswith("/") and not target.startswith("//") else url_for("home"))


@app.route("/message-board", methods=["GET", "POST"])
def message_board():
    if request.method == "POST":
        if not session.get("user_id"):
            return redirect(url_for("login", next=url_for("message_board")))
        content = request.form.get("content", "").strip()
        if not 1 <= len(content) <= 1000:
            flash("留言内容需为 1–1000 个字符", "error")
        else:
            store.add_message(session["user_id"], session["username"], content)
            flash("留言已发布", "success")
            return redirect(url_for("message_board"))
    return render_template("messages/index.html", messages=store.list_messages())


@app.get("/admin")
@admin_required
def admin():
    return render_template("admin/index.html", articles=store.list_articles(), users=store.list_users() if session.get("role") == "superadmin" else [], comments=store.list_comments(), messages=store.list_messages())


@app.post("/admin/comments/<int:comment_id>/delete")
@admin_required
def delete_comment(comment_id: int):
    store.delete_comment(comment_id)
    flash("评论已删除", "success")
    return redirect(url_for("admin") + "#community")


@app.post("/admin/messages/<int:message_id>/delete")
@admin_required
def delete_message(message_id: int):
    store.delete_message(message_id)
    flash("留言已删除", "success")
    return redirect(url_for("admin") + "#community")


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
        data = {key: request.form.get(key, "").strip() for key in ("title", "category", "summary", "external_url", "created_at")}
        data["direct_link"] = True
        data["content"] = ""
        data["external_label"] = "打开链接"
        data["published"] = request.form.get("published") == "on"
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["created_at"]):
                raise ValueError
            datetime.strptime(data["created_at"], "%Y-%m-%d")
        except ValueError:
            flash("请选择有效的显示日期", "error")
            return render_template("admin/editor.html", article=data, mode="new")
        if not valid_direct_url(data["external_url"]):
            flash("请填写完整的 http 或 https 跳转链接", "error")
            return render_template("admin/editor.html", article=data, mode="new")
        if len(data["title"]) < 2 or len(data["summary"]) < 10:
            flash("标题至少 2 个字，摘要至少 10 个字", "error")
            return render_template("admin/editor.html", article=data, mode="new")
        item = store.create_article(**data, slug=slugify(data["title"]))
        flash("文章已发布", "success")
        return redirect(url_for("admin") + "#recent-stories")
    return render_template("admin/editor.html", article={"created_at": datetime.now().strftime("%Y-%m-%d")}, mode="new")


@app.route("/admin/articles/<int:article_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_article(article_id: int):
    item = store.get_article_by_id(article_id)
    if not item:
        abort(404)
    if request.method == "POST":
        data = {key: request.form.get(key, "").strip() for key in ("title", "category", "summary", "external_url", "created_at")}
        data["direct_link"] = True
        data["content"] = item["content"]
        data["external_label"] = item["external_label"] or "打开链接"
        data["published"] = request.form.get("published") == "on"
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["created_at"]):
                raise ValueError
            datetime.strptime(data["created_at"], "%Y-%m-%d")
        except ValueError:
            flash("请选择有效的显示日期", "error")
            return render_template("admin/editor.html", article={**item, **data}, mode="edit")
        if not valid_direct_url(data["external_url"]):
            flash("请填写完整的 http 或 https 跳转链接", "error")
            return render_template("admin/editor.html", article={**item, **data}, mode="edit")
        if len(data["title"]) < 2 or len(data["summary"]) < 10:
            flash("标题至少 2 个字，摘要至少 10 个字", "error")
            return render_template("admin/editor.html", article={**item, **data}, mode="edit")
        store.update_article(article_id, **data)
        flash("文章已更新", "success")
        return redirect(url_for("admin"))
    return render_template("admin/editor.html", article=item, mode="edit")


@app.post("/admin/media/upload")
@admin_required
def upload_media():
    files = request.files.getlist("media")
    uploaded = 0
    upload_dir = BASE_DIR / "media" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    for item in files:
        suffix = Path(item.filename or "").suffix.lower()
        if item and suffix in ALLOWED_MEDIA_EXTENSIONS:
            filename = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}{suffix}"
            item.save(upload_dir / filename)
            uploaded += 1
    flash(f"已上传 {uploaded} 个媒体文件" if uploaded else "未找到支持的图片或视频", "success" if uploaded else "error")
    target = request.form.get("return_to", "")
    return redirect(target if target.startswith("/admin/") and not target.startswith("//") else url_for("admin"))


@app.route("/admin/pages/gsing", methods=["GET", "POST"])
@admin_required
def edit_gsing_page():
    settings = store.get_page_settings("gsing")
    if request.method == "POST":
        external_url = request.form.get("external_url", "").strip()
        external_label = request.form.get("external_label", "").strip() or "联系我们"
        content = request.form.get("content", "").strip()
        if not valid_external_url(external_url):
            flash("直接跳转需填写完整的 http 或 https 链接；文章内按钮另支持 weixin://", "error")
        else:
            store.update_page_settings("gsing", external_url, external_label, content)
            flash("GSing 专题页链接已更新", "success")
            return redirect(url_for("edit_gsing_page"))
    return render_template("admin/gsing_page.html", settings=settings, media_files=uploaded_media())


@app.post("/admin/articles/<int:article_id>/toggle")
@admin_required
def toggle_article(article_id: int):
    flash("动态发布状态已更新" if store.toggle_article_published(article_id) else "动态不存在", "success")
    return redirect(url_for("admin") + "#recent-stories")


@app.post("/admin/articles/<int:article_id>/delete")
@admin_required
def delete_article(article_id: int):
    store.delete_article(article_id)
    flash("文章已删除", "success")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    port = int(os.environ.get("PORT", "2024"))
    print("\n" + "=" * 60)
    print(f"🚀 服务启动成功！ {STARTED_AT:%Y-%m-%d %H:%M:%S}")
    print("=" * 60)
    print(f"📌 本地访问: http://localhost:{port}")
    print(f"📌 登录页面: http://localhost:{port}/login")
    print(f"📌 管理后台: http://localhost:{port}/admin")
    print(f"📌 根目录: {BASE_DIR}")
    print("📌 真实IP获取: ✅ CF-Connecting-IP / X-Real-IP / X-Forwarded-For")
    print("=" * 60)
    print("📊 访问日志格式: 日期时间 图标 用户 [真实IP] [城市] | 方法 路径 | 状态 | 耗时 | 访问量")
    print(f"📊 访问记录保存: data/site.db（SQLite，当前 {store.get_visit_count()} 条）")
    print(f"📊 本次日志文件: {ACCESS_LOG_PATH}")
    print("📊 路径格式: 中文路径直接显示")
    print("=" * 60 + "\n")
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
