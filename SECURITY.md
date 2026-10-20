# Security Policy

简体中文版本：[SECURITY.zh-CN.md](SECURITY.zh-CN.md)

## Supported versions

| Version | Supported |
| --- | --- |
| `main` (latest commit) | ✅ |
| Released tags | ✅ fixes are released as a new tag |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

1. Use GitHub's private "Report a vulnerability" form on the Security tab, or
   contact the maintainers directly.
2. Include a description of the issue, the affected endpoint or file, the steps
   to reproduce it and, if possible, a proof of concept.
3. You will receive an acknowledgement within 7 days and a status update at
   least every 14 days until the report is resolved.

We will credit reporters after a fix is released, unless anonymity is requested.

## Hardening notes for deployments

The repository ships development-friendly defaults that **must** be changed in
production:

| Setting | Development default | Production |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | insecure placeholder | unique random value, injected through the environment |
| `DJANGO_DEBUG` | `True` | `False` |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | your real host names |
| Database | SQLite file | PostgreSQL / MySQL with credentials in the environment |

Further recommendations:

* `db.sqlite3`, `.env` and `*.mo` files are git-ignored — keep it that way.
* Serve the application over HTTPS and set `SECURE_SSL_REDIRECT`,
  `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE`.
* Run `python manage.py check --deploy` before going live.
* Every page except the login page requires authentication
  (`LoginRequiredMiddleware`); review `LOGIN_EXEMPT_URLS` if you add routes.
* Uploaded files are parsed with pandas/openpyxl — restrict upload size at the
  reverse proxy as well.
