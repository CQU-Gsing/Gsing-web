# 维护与手动运行

服务由维护者手动启动或重启。开发助手不自动启动、重启服务。

在项目根目录中执行：

```powershell
python -m pip install -r requirements.txt
python -u main.py
```

默认访问 `http://127.0.0.1:2024`，在运行终端按 `Ctrl+C` 停止。Windows 也可手动运行根目录的 `web.cmd`，使用前核对其中的 Conda 路径与环境名称。

配置项名称见 `.env.example`；程序不会自动加载 `.env`，需在运行环境设置。不要在文档中记录实际账号密码或邮件授权码。

默认不启用自动重载。修改 Python 或模板后，由维护者手动重启。

## 检查

```powershell
python -m unittest discover -s tests -v
```

测试使用临时 SQLite 数据库和 Flask 测试客户端，不监听端口，不修改运行数据库，不启动服务。

目录职责见 [项目目录说明](project-structure.md)，变更记录见 [更新日志](../CHANGELOG.md)。
