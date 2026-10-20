# 安全策略

English version: [SECURITY.md](SECURITY.md)

## 受支持的版本

| 版本 | 是否支持 |
| --- | --- |
| `main`（最新提交） | ✅ |
| 已发布的 tag | ✅ 修复会以新 tag 发布 |

## 报告漏洞

**请勿通过公开 Issue 报告安全问题。**

1. 使用 GitHub Security 页面的 "Report a vulnerability" 私密表单，
   或直接联系维护者。
2. 请提供问题描述、受影响的文件或接口、复现步骤，尽量附上验证代码。
3. 我们会在 7 天内确认收到，并在处理期间至少每 14 天同步一次进展。

修复发布后会致谢报告者，除非对方要求匿名。

## 部署安全建议

仓库中的默认值面向开发调试，生产环境**必须**修改：

| 配置项 | 开发默认值 | 生产环境 |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | 不安全的占位值 | 随机唯一值，通过环境变量注入 |
| `DJANGO_DEBUG` | `True` | `False` |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | 真实主机名 |
| 数据库 | SQLite 文件 | PostgreSQL / MySQL，凭据放环境变量 |

其他建议：

* `db.sqlite3`、`.env` 与 `*.mo` 已被 git 忽略，请保持。
* 使用 HTTPS，并配置 `SECURE_SSL_REDIRECT`、`SESSION_COOKIE_SECURE`、`CSRF_COOKIE_SECURE`。
* 上线前执行 `python manage.py check --deploy`。
* 除登录页外所有页面都要求登录（`LoginRequiredMiddleware`）；
  新增路由时请同步检查 `LOGIN_EXEMPT_URLS`。
* 上传文件由 pandas/openpyxl 解析，建议在反向代理层再限制一次上传大小。
