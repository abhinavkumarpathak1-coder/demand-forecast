# Architecture

* [1. Request flow](#1-request-flow)
* [2. Apps](#2-apps)
* [3. Data model](#3-data-model)
* [4. Training and forecasting pipeline](#4-training-and-forecasting-pipeline)
* [5. Algorithms](#5-algorithms)
* [6. Endpoints](#6-endpoints)
* [7. Configuration and middleware](#7-configuration-and-middleware)
* [8. Known limitations](#8-known-limitations)

---

## 1. Request flow

```
Browser
   │
   ▼
Django URL dispatcher (config/urls.py)
   │
   ├─► core            home page + middleware
   ├─► data_management Excel import / CRUD / export
   ├─► data_insight    aggregation queries → Chart.js
   ├─► model_training  training engine → ForecastModel + ForecastResult
   ├─► demand_prediction forecast execution, adjustment, What-If
   └─► user_management login / logout
   │
   ▼
SQLite (default) ── pandas / numpy ── statsmodels · prophet · sklearn · xgboost · tensorflow
```

All pages except the login page and the static/media/i18n prefixes are protected
by `LoginRequiredMiddleware`.

## 2. Apps

| App | Responsibility | Has models |
| --- | --- | --- |
| `apps.core` | Home page, `CharsetMiddleware`, `LoginRequiredMiddleware`, `SystemLog` | yes |
| `apps.data_management` | Excel upload, browse/filter, inline adjustment, export, templates | yes |
| `apps.data_insight` | Aggregations for the dashboard (no persistence) | no |
| `apps.model_training` | Training engine, 14 algorithms, model metadata and results | yes |
| `apps.demand_prediction` | Forecast execution, manual adjustment, scenarios, What-If | yes |
| `apps.user_management` | Login, logout, placeholder registration/dashboard/permissions | no |

## 3. Data model

| Model | App | Key fields |
| --- | --- | --- |
| `ProductData` | data_management | `material_number` (unique), `material_name`, `product_category_level1..5` |
| `SalesData` | data_management | FK `product_data`, `sales_region_code/name`, `date`, `sales_quantity` |
| `PromotionData` | data_management | FK `product_data`, `sales_region_code/name`, `date`, `promotion_strength`, `promotion_start_date`, `promotion_end_date` |
| `ForecastModel` | model_training | `sales_region_code`, `material_number`, `model_type`, `hierarchy_level`, `category_code` (unique together), `accuracy`, `mae`, `rmse`, `is_overfit`, `training_start/end_date` |
| `ForecastResult` | model_training | FK `model`, `date`, `actual_quantity`, `forecast_quantity`, `adjusted_forecast_quantity`, `promotion_strength`, `model_used`, denormalised `category_l1..l5` |
| `ForecastScenario` | demand_prediction | `region`, `sku`, `forecast_period`, `hierarchy_level`, `promotion_type/value` |
| `SystemLog` | core | `action`, `user`, `timestamp`, `details` |

Indexes: `SalesData` on `(date, sales_region_code, product_data)`,
`PromotionData` on `(date, sales_region_code, product_data)`.

## 4. Training and forecasting pipeline

`apps/model_training/views.py`

1. **Resolve targets** — `_resolve_training_items()` expands the selected
   hierarchy level and regions into region × item combinations.
2. **Load series** — query the fact table (SKU level or a category level via
   `CATEGORY_FIELD_MAP`), resample to daily frequency with zero fill, then
   aggregate monthly.
3. **Clean** — `_preprocess_time_series()` handles gaps and outliers.
4. **Evaluate** — the last three months are held out; MAE, RMSE and accuracy
   (actual-based, to avoid division by zero) are computed.
5. **Anti-overfitting** — up to three retries with progressively simpler
   parameters (`_get_retry_params()`), then fallback model types.
6. **Blend** — `_try_ensemble()` weights the survivors by inverse MAE, applies
   trend/seasonality decomposition and a seasonal bias correction.
7. **Persist** — only the best model survives; the other models and their
   results are deleted.

`apps/demand_prediction/views.py`

* `demand_forecast()` resolves the requested combinations, falls back to a
  different hierarchy level when a SKU has no model, and triggers training when
  nothing exists.
* `_calculate_promotion_elasticity()` compares monthly averages with and without
  promotions; `what_if_analysis()` applies it to the baseline forecast.

## 5. Algorithms

| Type | Implementation | Dependency |
| --- | --- | --- |
| `holt-winters` | statsmodels ExponentialSmoothing | statsmodels |
| `arima`, `arimax` | statsmodels SARIMAX (+ exogenous promotion regressor) | statsmodels |
| `exp_smooth` | statsmodels simple exponential smoothing | statsmodels |
| `prophet` | Meta Prophet | prophet |
| `random_forest` | sklearn RandomForestRegressor | scikit-learn |
| `xgboost` | XGBRegressor on lag features | xgboost |
| `lstm`, `deepar` | Keras Sequential reference models | tensorflow |
| `moving_avg`, `weighted_avg`, `seasonal_naive`, `croston`, `sba` | in-project implementations | none |

`_get_available_model_types()` probes the imports at runtime, so a missing
dependency simply hides the corresponding algorithm.

## 6. Endpoints

| URL | Name | Method | Purpose |
| --- | --- | --- | --- |
| `/` | `home` | GET | Home page |
| `/data/upload/` | `data:upload` | GET/POST | Upload Excel files |
| `/data/view/` | `data:view_data` | GET | Browse and filter |
| `/data/adjust/` | `data:adjust_data` | GET/POST | Edit recent records |
| `/data/export/` | `data:export_data` | GET | Export to Excel |
| `/data/download-sales-template/` | `data:download_sales_template` | GET | Sales template |
| `/data/download-promotion-template/` | `data:download_promotion_template` | GET | Promotion template |
| `/insight/` | `insight:index` | GET | Dashboard |
| `/model/train/` | `model:train` | GET/POST | Training page and AJAX training |
| `/model/results/` | `model:results` | GET | Model list and evaluation |
| `/forecast/` | `forecast:forecast` | GET/POST | Forecast page and AJAX forecast |
| `/forecast/results/` | `forecast:results_page` | GET | Result page |
| `/forecast/export/` | `forecast:export` | POST | Excel export |
| `/forecast/update_adjusted_forecast/` | `forecast:update_adjusted_forecast` | POST | Save a manual adjustment |
| `/forecast/scenario/<id>/` | `forecast:load_scenario` | GET | Reload a saved scenario |
| `/forecast/api/refresh-models/` | `forecast:refresh_models` | GET | JSON list of recent models |
| `/forecast/what-if/` | `forecast:what_if` | GET/POST | What-If simulation |
| `/i18n/setlang/` | `set_language` | POST | Switch UI language |
| `/user/login/`, `/user/logout/` | | | Authentication |

The AJAX endpoints return `{"success": true|false, ...}` JSON.

## 7. Configuration and middleware

`config/settings.py`

* `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` and `LANGUAGE_CODE` are read from the
  environment (see [installation.md](installation.md)).
* `LANGUAGES` — `en` (default) and `zh-hans`; catalogs live in `locale/`.
* Middleware order matters: `SessionMiddleware` → `LocaleMiddleware` →
  `CharsetMiddleware` → ... → `LoginRequiredMiddleware`.

`apps/core/middleware.py`

* `CharsetMiddleware` forces `Content-Type: ...; charset=utf-8` and sets
  `Content-Language` from the active language.
* `LoginRequiredMiddleware` redirects anonymous users to `LOGIN_URL`, except for
  the patterns in `LOGIN_EXEMPT_URLS`.

## 8. Known limitations

* The forecasting engine lives in `views.py` (~114 KB) instead of a service
  layer; refactoring is on the roadmap.
* LSTM / DeepAR are reference implementations, not tuned models.
* `user_management` and `SystemLog` are placeholders.
* `forecast_period` is configurable up to 24 months while several model
  implementations still generate a fixed 12-month horizon.
* There is no automated test suite yet; `python manage.py check` and a manual
  smoke test are the current safety net.
