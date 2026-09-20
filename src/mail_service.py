"""GSing 邮箱验证码发送服务。"""
import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

logger = logging.getLogger("gsing.mail")
ROOT = Path(__file__).resolve().parent.parent


def _auth_code():
    value = os.environ.get("QQ_MAIL_AUTH_CODE", "").strip()
    if value:
        return value
    try:
        return (ROOT / "data" / "qq_mail_auth_code.txt").read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


def send_verify_code(to_email: str, code: str, purpose: str):
    sender = os.environ.get("QQ_MAIL_USER", "2361542526@qq.com").strip()
    auth_code = _auth_code()
    if not auth_code:
        return False, "邮件服务未配置：请设置 QQ_MAIL_AUTH_CODE"
    title = "GSing 战队账号验证码"
    action = "注册" if purpose == "register" else "登录"
    content = f"""你正在进行 GSing 战队网站账号{action}。

验证码：{code}

验证码 5 分钟内有效，请勿泄露给他人。
如非本人操作，请忽略此邮件。
"""
    message = MIMEText(content, "plain", "utf-8")
    message["From"] = formataddr(("GSing 机器人战队", sender))
    message["To"] = to_email
    message["Subject"] = title
    try:
        with smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=30) as server:
            server.login(sender, auth_code)
            server.sendmail(sender, [to_email], message.as_string())
        logger.info("验证码邮件已发送")
        return True, "验证码发送成功，请查收邮箱"
    except smtplib.SMTPAuthenticationError:
        logger.exception("QQ 邮箱认证失败")
        return False, "邮箱授权码错误"
    except Exception:
        logger.exception("验证码邮件发送失败")
        return False, "邮件发送失败，请稍后重试"
