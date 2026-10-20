# 贡献指南

感谢你愿意参与贡献！本文说明如何搭建开发环境，以及我们对 Pull Request 的基本要求。
English version: [CONTRIBUTING.md](CONTRIBUTING.md)

## 1. 环境准备

```bash
git clone <你的仓库地址> demand_forecast
cd demand_forecast
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py compilemessages
python manage.py createsuperuser
python manage.py runserver
```

编译翻译文件需要 GNU gettext（`brew install gettext` / `apt-get install gettext`）。

## 2. 开发流程

1. Fork 仓库并新建分支：`feature/简短描述`、`fix/简短描述`、`docs/简短描述`
   或 `i18n/简短描述`。
2. 一个提交只做一件事，提交信息用英文祈使句（如 `Add Croston bootstrap option`）。
3. 提交 Pull Request 前请确认：
   * `python manage.py check` 通过；
   * 若改动了界面文案，执行
     `python manage.py makemessages -l en -l zh_Hans --ignore=".venv/*"`，
     补全翻译后运行 `python scripts/sync_zh_catalog.py`；
   * `python manage.py compilemessages`；
   * 在**英文与简体中文**两种语言下都验证过。
4. 按模板填写 Pull Request，说明改动内容、原因以及验证方式。

## 3. 代码规范

* 遵循 PEP 8，并保持所在文件的既有风格。
* 业务逻辑放在对应的 app 中；可复用的辅助函数放在该 app 的 `utils.py` / `services.py`。
* 不要提交密钥、`db.sqlite3`、`.env`、`__pycache__` 和编译产物 `*.mo`，
  `.gitignore` 已覆盖这些文件。
* 系统只处理销售数据，请勿记录或导出任何个人信息。

## 4. 翻译规范

所有面向用户的文案都需要可翻译，详见 [docs/zh/i18n.md](docs/zh/i18n.md)：

* 模板：`{% load i18n %}` + `{% translate "中文" %}`
* Python：`from django.utils.translation import gettext as _`
  （模型与表单中使用 `gettext_lazy`）
* 字面 `%` 要放在 `{% translate %}` 标签之外
* `<script>` 中只翻译字符串字面量
* 同时更新 `en` 与 `zh_Hans` 两份目录

## 5. 提交问题与需求

请使用 GitHub Issue 模板。一份好的缺陷报告应包含复现步骤、期望结果、实际结果，
以及 Python/Django 版本与浏览器信息。如果是预测效果问题，请附上数据规模
（月份数、区域数、SKU 数），有样例数据最好。

## 6. 行为准则

参与本项目即表示你同意遵守 [行为准则](CODE_OF_CONDUCT.zh-CN.md)。

## 7. 许可证

贡献内容同样以 [MIT License](LICENSE) 发布。
