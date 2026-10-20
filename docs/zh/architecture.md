# 架构说明

* [1. 请求链路](#1-请求链路)
* [2. 应用划分](#2-应用划分)
* [3. 数据模型](#3-数据模型)
* [4. 训练与预测流程](#4-训练与预测流程)
* [5. 算法清单](#5-算法清单)
* [6. 接口清单](#6-接口清单)
* [7. 配置与中间件](#7-配置与中间件)
* [8. 已知限制](#8-已知限制)

---

## 1. 请求链路

```
浏览器
   │
   ▼
Django 路由 (config/urls.py)
   │
   ├─► core              首页与中间件
   ├─► data_management   Excel 导入 / 增删改 / 导出
   ├─► data_insight      聚合查询 → Chart.js
   ├─► model_training    训练引擎 → ForecastModel + ForecastResult
   ├─► demand_prediction 预测执行、人工调整、What-If
   └─► user_management   登录 / 登出
   │
   ▼
SQLite（默认）── pandas / numpy ── statsmodels · prophet · sklearn · xgboost · tensorflow
```

除登录页以及 static / media / i18n 前缀外，所有页面都由
`LoginRequiredMiddleware` 保护。

## 2. 应用划分

| 应用 | 职责 | 是否有模型 |
| --- | --- | --- |
| `apps.core` | 首页、`CharsetMiddleware`、`LoginRequiredMiddleware`、`SystemLog` | 有 |
| `apps.data_management` | Excel 上传、浏览筛选、行内调整、导出、模板下载 | 有 |
| `apps.data_insight` | 看板聚合查询（不落库） | 无 |
| `apps.model_training` | 训练引擎、14 种算法、模型元数据与预测结果 | 有 |
| `apps.demand_prediction` | 预测执行、人工调整、场景保存、What-If | 有 |
| `apps.user_management` | 登录、登出，以及占位的注册/仪表盘/权限页 | 无 |

## 3. 数据模型

| 模型 | 应用 | 关键字段 |
| --- | --- | --- |
| `ProductData` | data_management | `material_number`（唯一）、`material_name`、`product_category_level1..5` |
| `SalesData` | data_management | 外键 `product_data`、`sales_region_code/name`、`date`、`sales_quantity` |
| `PromotionData` | data_management | 外键 `product_data`、`sales_region_code/name`、`date`、`promotion_strength`、`promotion_start_date`、`promotion_end_date` |
| `ForecastModel` | model_training | `sales_region_code`、`material_number`、`model_type`、`hierarchy_level`、`category_code`（联合唯一）、`accuracy`、`mae`、`rmse`、`is_overfit`、`training_start/end_date` |
| `ForecastResult` | model_training | 外键 `model`、`date`、`actual_quantity`、`forecast_quantity`、`adjusted_forecast_quantity`、`promotion_strength`、`model_used`，冗余 `category_l1..l5` |
| `ForecastScenario` | demand_prediction | `region`、`sku`、`forecast_period`、`hierarchy_level`、`promotion_type/value` |
| `SystemLog` | core | `action`、`user`、`timestamp`、`details` |

索引：`SalesData` 与 `PromotionData` 均在 `(date, sales_region_code, product_data)` 上建索引。

## 4. 训练与预测流程

`apps/model_training/views.py`

1. **解析目标** —— `_resolve_training_items()` 把所选层级与区域展开为「区域 × 产品」组合。
2. **取数** —— 查询事实表（SKU 级或经 `CATEGORY_FIELD_MAP` 的分类级），
   按天补零后汇总为月度序列。
3. **清洗** —— `_preprocess_time_series()` 处理缺失与异常。
4. **评估** —— 最后三个月作为测试集，计算 MAE、RMSE 与准确率（以实际值为分母避免除零）。
5. **防过拟合** —— 最多重试三次，逐步降低复杂度（`_get_retry_params()`），
   必要时切换到回退算法。
6. **融合** —— `_try_ensemble()` 按 MAE 倒数加权，结合趋势-季节分解与季节性偏差校正。
7. **落库** —— 只保留最优模型，其余模型及其预测结果会被删除。

`apps/demand_prediction/views.py`

* `demand_forecast()` 解析组合；某 SKU 没有模型时按层级回退；完全没有模型时自动触发训练。
* `_calculate_promotion_elasticity()` 对比「有促销 / 无促销」的月均销量得到弹性系数，
  `what_if_analysis()` 把它应用到基线预测上。

## 5. 算法清单

| 类型 | 实现 | 依赖 |
| --- | --- | --- |
| `holt-winters` | statsmodels ExponentialSmoothing | statsmodels |
| `arima`、`arimax` | statsmodels SARIMAX（`arimax` 引入促销外生变量） | statsmodels |
| `exp_smooth` | statsmodels 简单指数平滑 | statsmodels |
| `prophet` | Meta Prophet | prophet |
| `random_forest` | sklearn RandomForestRegressor | scikit-learn |
| `xgboost` | 基于滞后特征的 XGBRegressor | xgboost |
| `lstm`、`deepar` | Keras Sequential 参考实现 | tensorflow |
| `moving_avg`、`weighted_avg`、`seasonal_naive`、`croston`、`sba` | 项目内实现 | 无 |

`_get_available_model_types()` 在运行时探测依赖，缺哪个包就隐藏对应算法。

## 6. 接口清单

| URL | 名称 | 方法 | 用途 |
| --- | --- | --- | --- |
| `/` | `home` | GET | 首页 |
| `/data/upload/` | `data:upload` | GET/POST | 上传 Excel |
| `/data/view/` | `data:view_data` | GET | 浏览筛选 |
| `/data/adjust/` | `data:adjust_data` | GET/POST | 编辑最近记录 |
| `/data/export/` | `data:export_data` | GET | 导出 Excel |
| `/data/download-sales-template/` | `data:download_sales_template` | GET | 销售模板 |
| `/data/download-promotion-template/` | `data:download_promotion_template` | GET | 促销模板 |
| `/insight/` | `insight:index` | GET | 数据洞察看板 |
| `/model/train/` | `model:train` | GET/POST | 训练页面与 AJAX 训练 |
| `/model/results/` | `model:results` | GET | 模型列表与评估 |
| `/forecast/` | `forecast:forecast` | GET/POST | 预测页面与 AJAX 预测 |
| `/forecast/results/` | `forecast:results_page` | GET | 预测结果页 |
| `/forecast/export/` | `forecast:export` | POST | 导出 Excel |
| `/forecast/update_adjusted_forecast/` | `forecast:update_adjusted_forecast` | POST | 保存人工调整值 |
| `/forecast/scenario/<id>/` | `forecast:load_scenario` | GET | 载入已保存场景 |
| `/forecast/api/refresh-models/` | `forecast:refresh_models` | GET | 最近模型 JSON |
| `/forecast/what-if/` | `forecast:what_if` | GET/POST | What-If 模拟 |
| `/i18n/setlang/` | `set_language` | POST | 切换界面语言 |
| `/user/login/`、`/user/logout/` | | | 登录与登出 |

AJAX 接口统一返回 `{"success": true|false, ...}` 形式的 JSON。

## 7. 配置与中间件

`config/settings.py`

* `SECRET_KEY`、`DEBUG`、`ALLOWED_HOSTS`、`LANGUAGE_CODE` 均从环境变量读取
  （见 [installation.md](installation.md)）。
* `LANGUAGES` —— `en`（默认）与 `zh-hans`，翻译目录为 `locale/`。
* 中间件顺序有要求：`SessionMiddleware` → `LocaleMiddleware` →
  `CharsetMiddleware` → … → `LoginRequiredMiddleware`。

`apps/core/middleware.py`

* `CharsetMiddleware` 强制 `Content-Type: ...; charset=utf-8`，并按当前语言设置 `Content-Language`。
* `LoginRequiredMiddleware` 把未登录用户重定向到 `LOGIN_URL`，
  `LOGIN_EXEMPT_URLS` 中的规则除外。

## 8. 已知限制

* 预测引擎集中在 `views.py`（约 114 KB），尚未拆分为服务层。
* LSTM / DeepAR 属于参考实现，未做深度调优。
* `user_management` 与 `SystemLog` 仍是占位实现。
* `forecast_period` 最多支持 24 个月，但部分模型实现内部仍固定生成 12 个月。
* 目前缺少自动化测试，主要依赖 `python manage.py check` 与人工冒烟验证。
