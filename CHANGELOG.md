# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
简体中文版本：[CHANGELOG.zh-CN.md](CHANGELOG.zh-CN.md)

## [Unreleased]

### Added

* Multilingual user interface: English (default), 中文, Français, Deutsch,
  Español and 日本語, switchable at runtime from the top right selector.
* Translation catalogs for all six languages plus
  `scripts/sync_zh_catalog.py`, which keeps the Simplified Chinese catalog in
  sync with the source strings.
* Locale aware date rendering (`localize_date` / `localize_month` template
  filters) so months and dates follow the active language.
* `apps.core.context_processors.languages` exposes `AVAILABLE_LANGUAGES_NATIVE`
  so the switcher can list every language in its own language.
* Documentation set in English and Chinese: README, installation, usage,
  architecture and translations guides.
* Community health files: `LICENSE` (MIT), `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, `SECURITY.md`, issue/PR templates and a GitHub Actions
  workflow.
* `.env.example` and environment-driven configuration for `SECRET_KEY`,
  `DEBUG`, `ALLOWED_HOSTS` and `LANGUAGE_CODE`.

### Changed

* The language switcher moved from the sidebar footer to the top right corner
  and now uses a high-contrast (amber) pill style.
* The account chip (username + log out) also moved from the sidebar footer to
  the top right bar.
* Dates in tables are rendered with the locale's date format instead of the
  language neutral `%Y-%m` / `%Y-%m-%d` output.
* Sidebar menu, page title and footer use translated strings as well, so the
  Simplified Chinese UI no longer shows English navigation entries.
* The default language is always `LANGUAGE_CODE` (`en`): the browser
  `Accept-Language` header is ignored unless `DJANGO_LANGUAGE_FROM_BROWSER` is
  enabled (`DefaultLanguageLocaleMiddleware`).
* `SECRET_KEY` is no longer hard-coded; it is read from `DJANGO_SECRET_KEY`
  (with an insecure development fallback).
* `DEBUG` and `ALLOWED_HOSTS` are no longer hard-coded `True` / `['*']`.
* `Content-Language` now follows the active language instead of always being
  `zh-CN`.
* `requirements.txt` uses minimum versions instead of exact pins and documents
  the optional algorithm dependencies.

### Security

* `db.sqlite3`, `.env`, `__pycache__`, `media/`, `staticfiles/` and compiled
  `*.mo` files are excluded from version control.
