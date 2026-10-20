# 安装部署

* [1. 环境要求](#1-环境要求)
* [2. 安装](#2-安装)
* [3. 配置](#3-配置)
* [4. 数据库](#4-数据库)
* [5. 翻译文件](#5-翻译文件)
* [6. 启动](#6-启动)
* [7. 生产部署](#7-生产部署)
* [8. 常见问题](#8-常见问题)

---

## 1. 环境要求

| 依赖 | 说明 |
| --- | --- |
| Python | 3.10 及以上（已在 3.13 验证） |
| Django | 4.2 及以上（已在 4.2.7 与 6.1 验证） |
| GNU gettext | `makemessages` / `compilemessages` 需要 |
| 磁盘 | 虚拟环境约 200 MB，另加数据空间 |

可选依赖会解锁更多预测算法：

| 包 | 启用算法 |
| --- | --- |
| `statsmodels>=0.14` | `arima`、`arimax`、`exp_smooth` |
| `prophet>=1.1` | `prophet` |
| `tensorflow>=2.13` | `lstm`、`deepar` |

安装 gettext：macOS `brew install gettext`；Debian/Ubuntu `apt-get install gettext`；
Fedora `dnf install gettext`。

## 2. 安装

```bash
git clone <你的仓库地址> demand_forecast
cd demand_forecast

python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

pip install --upgrade pip
pip install -r requirements.txt

# 可选算法依赖
pip install statsmodels prophet tensorflow
```

## 3. 配置

把 `.env.example` 复制为 `.env` 并按需修改。安装 `python-dotenv` 后
`config/settings.py` 会自动读取该文件；也可以直接导出同名环境变量。

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | 不安全的占位值 | **生产环境必须设置** |
| `DJANGO_DEBUG` | `True` | 生产环境设为 `False` |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | 逗号分隔的主机名 |
| `DJANGO_LANGUAGE_CODE` | `en` | 默认界面语言（`en` 或 `zh-hans`） |
| `DJANGO_LANGUAGE_FROM_BROWSER` | `False` | 设为 `True` 则按浏览器 `Accept-Language` 判定语言 |

生成密钥：

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

部署前还可以检查 `config/settings.py` 中的 `LOGIN_URL`、`LOGIN_REDIRECT_URL`
与 `LOGIN_EXEMPT_URLS`（`apps.core.middleware.LoginRequiredMiddleware` 使用）。

## 4. 数据库

默认使用 SQLite，适合评估与试用。正式使用建议改为 PostgreSQL 或 MySQL，
修改 `config/settings.py` 中的 `DATABASES`：

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

然后建表并创建第一个账号：

```bash
python manage.py migrate
python manage.py createsuperuser
```

`db.sqlite3` 已被 `.gitignore` 忽略，本地数据不会进入提交。

## 5. 翻译文件

编译产物（`*.mo`）属于构建结果，**不纳入版本管理**：

```bash
python manage.py compilemessages
```

如果不执行这一步，即便选择英文，界面也会回退到源语言（简体中文）。
完整流程见 [i18n.md](i18n.md)。

## 6. 启动

```bash
python manage.py runserver
```

访问 <http://127.0.0.1:8000/>。除登录页外所有页面都要求登录
（`LoginRequiredMiddleware`），请使用上面创建的超级用户登录。

示例数据在本地生成 —— 仓库不包含任何客户数据：

```bash
python scripts/generate_sample_data.py
```

该命令会生成 `TestData/sales_data.xlsx` 与 `TestData/promotion_data.xlsx`，
在「数据管理」页面依次上传这两个文件即可快速体验。

## 7. 生产部署

1. 设置 `DJANGO_DEBUG=False`、强随机 `DJANGO_SECRET_KEY` 与正确的 `DJANGO_ALLOWED_HOSTS`。
2. 执行 `python manage.py collectstatic`，由 Web 服务器（或 CDN）托管 `staticfiles/`。
3. 用应用服务器运行，例如 `gunicorn config.wsgi:application --bind 127.0.0.1:8000`。
4. 在 nginx/Apache 上终止 TLS，并转发 `X-Forwarded-For` / `X-Forwarded-Proto`，
   对应配置 `SECURE_PROXY_SSL_HEADER`。
5. `python manage.py check --deploy` 会列出剩余加固项（HTTPS Cookie、HSTS、
   `SECURE_SSL_REDIRECT` 等）。
6. 定期执行 `python manage.py clearsessions`。

## 8. 常见问题

| 现象 | 处理 |
| --- | --- |
| `command not found: msgfmt` | 安装 GNU gettext（见第 1 节） |
| 切换英文后界面仍是中文 | 执行 `python manage.py compilemessages` |
| numpy / pandas 报 `ImportError` | 重装 wheel：`pip install --force-reinstall numpy pandas` |
| 可选算法没有出现在列表里 | 安装对应依赖，系统会在运行时自动探测 |
| 登录后反复跳转 | 检查 `config/settings.py` 中的 `LOGIN_EXEMPT_URLS` |
