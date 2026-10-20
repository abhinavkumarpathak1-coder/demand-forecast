# Pull Request

## Summary / 变更说明

<!-- What does this PR change and why? -->

## Type / 类型

- [ ] Bug fix / 缺陷修复
- [ ] New feature / 新功能
- [ ] Refactor / 重构
- [ ] Documentation / 文档
- [ ] i18n / 多语言

## Checklist / 检查清单

- [ ] `python manage.py check` passes / 通过
- [ ] `python manage.py makemigrations --check --dry-run` shows no pending migration / 无待生成迁移
- [ ] User-visible text is wrapped with `{% translate %}` / `gettext()`
      （新增界面文案已做翻译标记）
- [ ] Ran `python manage.py makemessages -l en -l zh_Hans --ignore=".venv/*"`,
      filled in the English `msgstr`, then `python scripts/sync_zh_catalog.py`
      （已更新两份语言目录）
- [ ] `python manage.py compilemessages` executed / 已编译翻译
- [ ] Verified the change in **English and Simplified Chinese** / 已在中英双语下验证
- [ ] No secrets, `db.sqlite3`, `.env` or `*.mo` files are included / 未提交敏感文件

## How to test / 验证方式

<!-- Steps a reviewer can follow. -->
