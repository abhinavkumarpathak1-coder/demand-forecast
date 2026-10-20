# Installation

* [1. Requirements](#1-requirements)
* [2. Install](#2-install)
* [3. Configuration](#3-configuration)
* [4. Database](#4-database)
* [5. Translations](#5-translations)
* [6. Run](#6-run)
* [7. Production deployment](#7-production-deployment)
* [8. Troubleshooting](#8-troubleshooting)

---

## 1. Requirements

| Requirement | Notes |
| --- | --- |
| Python | 3.10 or newer (tested on 3.13) |
| Django | 4.2 or newer (tested on 4.2.7 and 6.1) |
| GNU gettext | Needed by `makemessages` / `compilemessages` |
| Disk | ~200 MB for the virtual environment, plus your data |

Optional Python packages unlock extra forecasting algorithms:

| Package | Enables |
| --- | --- |
| `statsmodels>=0.14` | `arima`, `arimax`, `exp_smooth` |
| `prophet>=1.1` | `prophet` |
| `tensorflow>=2.13` | `lstm`, `deepar` |

Install gettext with `brew install gettext` (macOS),
`apt-get install gettext` (Debian/Ubuntu) or `dnf install gettext` (Fedora).

## 2. Install

```bash
git clone <your-fork-url> demand_forecast
cd demand_forecast

python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

pip install --upgrade pip
pip install -r requirements.txt

# optional algorithms
pip install statsmodels prophet tensorflow
```

## 3. Configuration

Copy `.env.example` to `.env` and edit it. `config/settings.py` loads the file
automatically when `python-dotenv` is installed; otherwise the same values can
be exported as environment variables.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | insecure placeholder | **Must be set in production** |
| `DJANGO_DEBUG` | `True` | Set to `False` in production |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma separated host names |
| `DJANGO_LANGUAGE_CODE` | `en` | Default UI language (`en` or `zh-hans`) |
| `DJANGO_LANGUAGE_FROM_BROWSER` | `False` | `True` to let the browser `Accept-Language` header pick the language |

Generate a secret key:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Other settings worth reviewing before deployment: `LOGIN_URL`,
`LOGIN_REDIRECT_URL` and `LOGIN_EXEMPT_URLS` (used by
`apps.core.middleware.LoginRequiredMiddleware`), all in `config/settings.py`.

## 4. Database

SQLite is configured out of the box and is fine for evaluation. For anything
else, point `DATABASES` in `config/settings.py` at PostgreSQL or MySQL, e.g.:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'demand_forecast'),
        'USER': os.environ.get('POSTGRES_USER', 'postgres'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', ''),
        'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
    }
}
```

Then create the schema and the first account:

```bash
python manage.py migrate
python manage.py createsuperuser
```

`db.sqlite3` is git-ignored, so your local data never ends up in a commit.

## 5. Translations

The compiled catalogs (`*.mo`) are build artefacts and are **not** committed:

```bash
python manage.py compilemessages
```

Without this step the UI falls back to the source strings (Simplified Chinese),
even when English is selected. See [i18n.md](i18n.md) for the full workflow.

## 6. Run

```bash
python manage.py runserver
```

The app is served at <http://127.0.0.1:8000/>. Every page except the login page
requires authentication (`LoginRequiredMiddleware`), so log in with the
superuser created above.

Sample files for a first test run are generated locally - no customer data is
committed to the repository:

```bash
python scripts/generate_sample_data.py
```

The command writes `TestData/sales_data.xlsx` and `TestData/promotion_data.xlsx`;
upload both on the Data Management page.

## 7. Production deployment

1. `DJANGO_DEBUG=False`, a strong `DJANGO_SECRET_KEY` and a correct
   `DJANGO_ALLOWED_HOSTS`.
2. `python manage.py collectstatic` and serve `staticfiles/` through your web
   server (or a CDN).
3. Run with an application server, e.g.
   `gunicorn config.wsgi:application --bind 127.0.0.1:8000`.
4. Terminate TLS in nginx/Apache and forward `X-Forwarded-For` /
   `X-Forwarded-Proto`; add `SECURE_PROXY_SSL_HEADER` accordingly.
5. `python manage.py check --deploy` lists the remaining Django hardening steps
   (HTTPS cookies, HSTS, `SECURE_SSL_REDIRECT`, ...).
6. Schedule `python manage.py clearsessions` periodically.

## 8. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `command not found: msgfmt` | Install GNU gettext (see section 1) |
| UI stays Chinese after selecting English | Run `python manage.py compilemessages` |
| `ImportError` from numpy/pandas | Reinstall the wheels: `pip install --force-reinstall numpy pandas` |
| Optional algorithms missing from the list | Install the matching dependency; availability is detected at runtime |
| Login redirects in a loop | Check `LOGIN_EXEMPT_URLS` in `config/settings.py` |
