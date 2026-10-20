# Contributing

Thanks for taking the time to contribute! This document describes how to set up
a development environment and what we expect from a pull request.
简体中文版本：[CONTRIBUTING.zh-CN.md](CONTRIBUTING.zh-CN.md)

## 1. Getting started

```bash
git clone <your-fork-url> demand_forecast
cd demand_forecast
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py compilemessages
python manage.py createsuperuser
python manage.py runserver
```

You also need GNU gettext (`brew install gettext` / `apt-get install gettext`) to
compile the translation catalogs.

## 2. Workflow

1. Fork the repository and create a branch: `feature/short-summary`,
   `fix/short-summary`, `docs/short-summary` or `i18n/short-summary`.
2. Keep commits focused; write messages in English using the imperative mood
   (`Add Croston bootstrap option`).
3. Before opening a pull request:
   * `python manage.py check`
   * `python manage.py makemessages -l en -l zh_Hans --ignore=".venv/*"` if you
     touched user-visible text, then fill in the translations and run
     `python scripts/sync_zh_catalog.py`
   * `python manage.py compilemessages`
   * verify the change in **both** English and Simplified Chinese
4. Open the pull request using the template and describe *what* changed and
   *why*, plus how you tested it.

## 3. Coding guidelines

* Follow PEP 8; keep the existing style of the file you are editing.
* Business logic belongs in the owning app; reusable helpers may go into a
  `utils.py` / `services.py` inside that app.
* Do not commit secrets, `db.sqlite3`, `.env`, `__pycache__` or compiled `*.mo`
  files — `.gitignore` already covers them.
* Never log or export personal data; the application deals with sales data only.

## 4. Translation rules

All user-visible text must be translatable. See
[docs/en/i18n.md](docs/en/i18n.md):

* Templates: `{% load i18n %}` + `{% translate "中文" %}`
* Python: `from django.utils.translation import gettext as _` (use
  `gettext_lazy` in models and forms)
* Keep literal `%` outside `{% translate %}` tags
* Only translate string literals inside `<script>` blocks
* Update **both** catalogs (`en` and `zh_Hans`)

## 5. Reporting bugs and requesting features

Use the GitHub issue templates. A good bug report contains the steps to
reproduce, the expected and the actual result, your Python/Django version and
the browser you used. For forecasting quality issues, please include the shape
of the data (number of months, regions, SKUs) — sample data is very helpful.

## 6. Code of conduct

By participating you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).

## 7. License

Contributions are accepted under the [MIT License](LICENSE).
