# 项目目录说明

```text
GSing-web/
├── main.py                 # Flask 应用入口与路由
├── README.md               # 面向访客的战队介绍
├── CHANGELOG.md            # 网站更新记录
├── requirements.txt        # Python 依赖
├── web.cmd                 # 维护者手动启动脚本
├── content/
│   └── team.json           # 公开组别介绍、报名链接和成员资料
├── pages/                  # Jinja 模板，不存放原始私人名单
│   ├── base.html           # 全站基础模板
│   ├── shared/             # 公共页头
│   ├── home/               # 首页
│   ├── team/               # 历史获奖和历届队员
│   ├── groups/             # 五个组别介绍
│   ├── articles/           # 文章、独立证书页和证书组件
│   ├── login/              # 登录与注册
│   ├── messages/           # 留言板
│   └── admin/              # 后台管理
├── src/                    # 数据存储、邮件及 IP 归属地服务
│   └── ip2region-master/   # 第三方离线查询代码、数据和许可证
├── static/
│   ├── css/
│   │   ├── base.css        # 基础组件和通用布局
│   │   ├── home.css        # 首页布局
│   │   ├── team.css        # 组别与历史页面布局
│   │   ├── auth.css        # 登录注册布局
│   │   └── theme.css       # 全站深色主题，最后加载
│   └── js/                # 首页、导航、认证与媒体编辑交互
├── media/                  # 网站公开图片、证书及上传媒体
├── data/                   # 本地数据库与运行配置
├── logs/                   # 本地访问日志
├── tests/                  # 不启动服务的回归检查
└── docs/
    ├── development.md      # 维护与手动运行说明
    ├── project-structure.md
    └── private/            # 本地原始资料，Git 忽略，不用于网站发布
```

## 内容边界

- `content/team.json` 只保存可公开字段。成员资料允许姓名、职位、学院、专业、年级。
- `docs/private/team-source.md` 是原始名单，参考图片位于 `docs/private/references/`。不要将该目录复制到网站静态资源或发布目录。
- `.gitignore` 只能防止后续添加文件，不会清除已有 Git 历史中的资料。
- `data/`、`logs/` 和用户上传文件属于运行数据，整理代码时不移动或覆盖数据库。
- URL 路径保持不变，例如 `/projects/gsing/` 仍展示战队历史，模板文件调整不影响外部链接。

## 样式加载

基础模板先加载 `base.css`，再加载页面布局样式，最后加载 `theme.css`。共享主题负责配色、表单状态和导航；页面文件负责各自布局。修改资源后同步调整模板版本参数，避免浏览器旧缓存。
