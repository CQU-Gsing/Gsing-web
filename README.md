# 重庆大学 GSing 机器人战队网站

参照 `hyper-s-website-master` 的目录组织方式实现，后端使用 Python + Flask，文章和管理员账户存储在 SQLite。

## 功能

- 战队官网首页与移动端响应式布局
- 用户注册、登录与 Session 会话
- QQ 邮箱验证码注册与验证码登录
- 支持“邮箱或用户名 + 密码”登录
- 普通用户、管理员、终极管理员三级权限
- 终极管理员可授予/取消管理员权限并删除普通账户
- 文章发布、编辑、草稿和删除
- SQLite 持久化存储
- 终端实时访问日志，识别 Cloudflare 真实访客 IP
- 使用本地 ip2region IPv4/IPv6 数据库直接显示 IP 国家、省份、城市和运营商
- 每次启动生成独立的 `logs/access-YYYYMMDD-HHMMSS.log`，访问记录同时写入 SQLite `visits` 表
- SQLite 原子累计访问计数，重启后继续累计，并显示在官网页脚和每条访问日志中
- 自动初始化示例文章
- 使用 `media` 中的战队徽标、合影、机器人照片和招新海报

## 启动

```powershell
python -m pip install -r requirements.txt
python -u main.py
```

访问：`http://127.0.0.1:2024`

首次本地启动的默认管理员：

- 用户名：`admin`
- 密码：`gsing2024`

正式部署前请设置 `GSING_SECRET_KEY`、`GSING_ADMIN_USERNAME` 和 `GSING_ADMIN_PASSWORD` 环境变量。管理员仅在数据库首次创建时初始化；修改环境变量不会覆盖已有账户。

邮箱验证码默认通过 QQ 邮箱 SMTP SSL（`smtp.qq.com:465`）发送。发送账号由 `QQ_MAIL_USER` 配置，授权码优先读取 `QQ_MAIL_AUTH_CODE` 环境变量，否则读取被 Git 忽略的 `data/qq_mail_auth_code.txt`。

## 目录

```text
├── main.py                 # Flask 服务入口，默认端口 2024
├── requirements.txt       # Python 依赖
├── pages/                  # Jinja 页面
│   ├── home/               # 官网首页
│   ├── login/              # 管理员登录
│   ├── admin/              # 文章管理与编辑器
│   └── articles/           # 文章详情
├── src/
│   └── storage.py          # SQLite 存储、密码验证与文章 CRUD
├── static/
│   └── css/                # 网站样式
├── media/                  # 统一媒体目录
│   ├── home/               # 全站品牌图片
│   └── pages/Gsing/        # GSing 页面图片
└── data/
    └── site.db             # 运行后自动生成，不提交 Git
```
