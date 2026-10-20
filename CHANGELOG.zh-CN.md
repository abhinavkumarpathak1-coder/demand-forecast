# 更新日志

本文件记录项目的所有重要变更。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。
English version: [CHANGELOG.md](CHANGELOG.md)

## [未发布]

### 新增

* 多语言界面：默认英文，另有中文、Français、Deutsch、Español、日本語，
  可在运行时通过右上角下拉框切换。
* 六门语言的完整翻译目录，并提供 `scripts/sync_zh_catalog.py`
  用于同步简体中文目录。
* 本地化日期渲染（模板过滤器 `localize_date` / `localize_month`），
  月份与日期会跟随当前语言。
* `apps.core.context_processors.languages` 提供
  `AVAILABLE_LANGUAGES_NATIVE`，使切换器能以各语言自身名称显示。
* 中英文文档：README、安装部署、使用指南、架构说明与多语言说明。
* 开源社区文件：`LICENSE`（MIT）、`CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`、
  `SECURITY.md`、Issue/PR 模板以及 GitHub Actions 工作流。
* `.env.example`，以及 `SECRET_KEY`、`DEBUG`、`ALLOWED_HOSTS`、`LANGUAGE_CODE`
  的环境变量化配置。

### 变更

* 语言切换控件从侧边栏底部移到右上角，并改为高对比度（橙色）胶囊样式。
* 账号信息（用户名 + 退出登录）也从侧边栏底部移到右上角。
* 表格中的日期改为按当前语言格式化，不再是语言无关的 `%Y-%m` / `%Y-%m-%d`。
* 侧边栏菜单、页面标题与页脚文案也纳入翻译，中文界面不再残留英文导航项。
* 默认语言始终为 `LANGUAGE_CODE`（`en`）：除非开启
  `DJANGO_LANGUAGE_FROM_BROWSER`，否则忽略浏览器 `Accept-Language`
  （新增 `DefaultLanguageLocaleMiddleware`）。
* `SECRET_KEY` 不再硬编码，改为从 `DJANGO_SECRET_KEY` 读取
  （开发环境有不安全的兜底值）。
* `DEBUG` 与 `ALLOWED_HOSTS` 不再固定为 `True` / `['*']`。
* `Content-Language` 响应头跟随当前语言，不再固定为 `zh-CN`。
* `requirements.txt` 改为最低版本约束，并说明可选算法依赖。

### 安全

* `db.sqlite3`、`.env`、`__pycache__`、`media/`、`staticfiles/` 与编译产物
  `*.mo` 均已排除在版本控制之外。
