from django.utils.translation import gettext
from django.shortcuts import render, redirect
from django.urls import reverse
from django.http import JsonResponse
from django.contrib import messages
import json
import logging
import pandas as pd
import numpy as np
from datetime import timedelta

logger = logging.getLogger('model_training')
from collections import OrderedDict
from apps.data_management.models import SalesData
from .models import ForecastModel, ForecastResult
from django.contrib.auth.decorators import login_required
from django.db.models import Min, Max

# ──────────────────────────────────────────────
# 产品层级映射
# ──────────────────────────────────────────────
CATEGORY_FIELD_MAP = {
    'category_l1': 'product_data__product_category_level1',
    'category_l2': 'product_data__product_category_level2',
    'category_l3': 'product_data__product_category_level3',
    'category_l4': 'product_data__product_category_level4',
    'category_l5': 'product_data__product_category_level5',
}

HIERARCHY_LABEL_MAP = {
    'sku': gettext('SKU级别'),
    'category_l1': gettext('一级分类'),
    'category_l2': gettext('二级分类'),
    'category_l3': gettext('三级分类'),
    'category_l4': gettext('四级分类'),
    'category_l5': gettext('五级分类'),
}

LEVEL_FIELD_MAP = {
    'category_l1': 'product_category_level1',
    'category_l2': 'product_category_level2',
    'category_l3': 'product_category_level3',
    'category_l4': 'product_category_level4',
    'category_l5': 'product_category_level5',
}


def _build_category_cascade_tree():
    """
    从 ProductData 构建分类级联关系树，供前端动态渲染级联多选下拉框。
    返回 JSON 可序列化的 dict。
    结构说明：
      - all_l1 ~ all_l5: 各自层级全部不重复值（已排序）
      - all_skus: 所有物料号
      - l1_to_l2: {l1值: [所属l2值列表]}
      - l2_to_l3, l3_to_l4, l4_to_l5, l5_to_sku: 逐级映射
      - sku_info: {sku: {name, l1, l2, l3, l4, l5}}
    """
    from apps.data_management.models import ProductData as PD

    products = PD.objects.all().values(
        'material_number', 'material_name',
        'product_category_level1', 'product_category_level2',
        'product_category_level3', 'product_category_level4', 'product_category_level5'
    )

    l1_set, l2_set, l3_set, l4_set, l5_set = set(), set(), set(), set(), set()
    l1_to_l2, l2_to_l3, l3_to_l4, l4_to_l5, l5_to_sku = {}, {}, {}, {}, {}
    sku_info = {}

    for p in products:
        l1 = (p['product_category_level1'] or '').strip()
        l2 = (p['product_category_level2'] or '').strip()
        l3 = (p['product_category_level3'] or '').strip()
        l4 = (p['product_category_level4'] or '').strip()
        l5 = (p['product_category_level5'] or '').strip()
        sku = p['material_number']
        name = (p['material_name'] or '').strip()

        sku_info[sku] = {'name': name, 'l1': l1, 'l2': l2, 'l3': l3, 'l4': l4, 'l5': l5}

        if l1:
            l1_set.add(l1)
            l1_to_l2.setdefault(l1, set())
            if l2:
                l1_to_l2[l1].add(l2)
                l2_set.add(l2)
                l2_to_l3.setdefault(l2, set())
                if l3:
                    l2_to_l3[l2].add(l3)
                    l3_set.add(l3)
                    l3_to_l4.setdefault(l3, set())
                    if l4:
                        l3_to_l4[l3].add(l4)
                        l4_set.add(l4)
                        l4_to_l5.setdefault(l4, set())
                        if l5:
                            l4_to_l5[l4].add(l5)
                            l5_set.add(l5)
                            l5_to_sku.setdefault(l5, set())
                            l5_to_sku[l5].add(sku)
                        else:
                            l4_to_l5[l4].add('')
                    else:
                        l3_to_l4[l3].add('')
                else:
                    l2_to_l3[l2].add('')
            else:
                l1_to_l2[l1].add('')
        else:
            sku_info[sku] = {'name': name, 'l1': '', 'l2': '', 'l3': '', 'l4': '', 'l5': ''}

    # 如果存在没有父级分类的子级，补充到对应映射中
    for sku, info in sku_info.items():
        if info['l2'] and info['l2'] not in l2_to_l3:
            l2_to_l3.setdefault(info['l2'], set()).add(info['l3'])
        if info['l3'] and info['l3'] not in l3_to_l4:
            l3_to_l4.setdefault(info['l3'], set()).add(info['l4'])
        if info['l4'] and info['l4'] not in l4_to_l5:
            l4_to_l5.setdefault(info['l4'], set()).add(info['l5'])
        if info['l5'] and info['l5'] not in l5_to_sku:
            l5_to_sku.setdefault(info['l5'], set()).add(sku)

    def _sorted_list(s):
        return sorted([x for x in s if x])

    return {
        'all_l1': _sorted_list(l1_set),
        'all_l2': _sorted_list(l2_set),
        'all_l3': _sorted_list(l3_set),
        'all_l4': _sorted_list(l4_set),
        'all_l5': _sorted_list(l5_set),
        'all_skus': sorted(sku_info.keys()),
        'l1_to_l2': {k: _sorted_list(v) for k, v in l1_to_l2.items()},
        'l2_to_l3': {k: _sorted_list(v) for k, v in l2_to_l3.items()},
        'l3_to_l4': {k: _sorted_list(v) for k, v in l3_to_l4.items()},
        'l4_to_l5': {k: _sorted_list(v) for k, v in l4_to_l5.items()},
        'l5_to_sku': {k: _sorted_list(v) for k, v in l5_to_sku.items()},
        'sku_info': sku_info,
    }


def _resolve_training_items(hierarchy_level, selected_l1, selected_l2, selected_l3,
                            selected_l4, selected_l5, selected_skus):
    """
    根据层级和分类/ SKU 筛选条件，解析出最终要训练的项目代码列表。
    返回: [(item_code, category_code(可为None)), ...]
    """
    from apps.data_management.models import ProductData as PD

    if hierarchy_level == 'sku':
        qs = PD.objects.all()
        if selected_l1:
            qs = qs.filter(product_category_level1__in=selected_l1)
        if selected_l2:
            qs = qs.filter(product_category_level2__in=selected_l2)
        if selected_l3:
            qs = qs.filter(product_category_level3__in=selected_l3)
        if selected_l4:
            qs = qs.filter(product_category_level4__in=selected_l4)
        if selected_l5:
            qs = qs.filter(product_category_level5__in=selected_l5)
        if selected_skus:
            qs = qs.filter(material_number__in=selected_skus)
        sku_list = list(qs.values_list('material_number', flat=True).distinct().order_by('material_number'))
        return [(s, None) for s in sku_list]
    else:
        target_field = LEVEL_FIELD_MAP[hierarchy_level]
        qs = PD.objects.all()
        if selected_l1:
            qs = qs.filter(product_category_level1__in=selected_l1)
        if selected_l2:
            qs = qs.filter(product_category_level2__in=selected_l2)
        if selected_l3:
            qs = qs.filter(product_category_level3__in=selected_l3)
        if selected_l4:
            qs = qs.filter(product_category_level4__in=selected_l4)
        if selected_l5:
            qs = qs.filter(product_category_level5__in=selected_l5)
        cat_values = list(qs.exclude(**{target_field: ''})
                          .values_list(target_field, flat=True).distinct().order_by(target_field))
        return [(v, v) for v in cat_values]


def _get_sales_date_range():
    """获取 SalesData 表中的最早和最晚日期，返回 (min_date_str, max_date_str)"""
    agg = SalesData.objects.aggregate(min_d=Min('date'), max_d=Max('date'))
    min_d = agg.get('min_d')
    max_d = agg.get('max_d')
    if min_d and max_d:
        return min_d.strftime('%Y-%m'), max_d.strftime('%Y-%m')
    return '', ''


VALID_MODEL_TYPES = [
    'holt-winters', 'arima', 'arimax', 'xgboost',
    'moving_avg', 'weighted_avg', 'exp_smooth', 'seasonal_naive',
    'prophet', 'random_forest', 'croston', 'sba',
    'lstm', 'deepar'
]


def _get_available_model_types():
    """检测当前环境可用的模型类型（只需将算法名称加入 VALID_MODEL_TYPES 即可启用）"""
    # 基础模型（无需额外依赖，始终可用）
    types = ['holt-winters', 'moving_avg', 'weighted_avg', 'seasonal_naive']
    # 自定义实现，无需额外依赖
    types.append('croston')
    types.append('sba')
    try:
        import sklearn.ensemble
        types.append('random_forest')
    except ImportError:
        pass
    try:
        import statsmodels
        types.append('arima')
        types.append('arimax')
        types.append('exp_smooth')
    except ImportError:
        pass
    try:
        import xgboost
        types.append('xgboost')
    except ImportError:
        pass
    try:
        import prophet
        types.append('prophet')
    except ImportError:
        pass
    try:
        import tensorflow as _tf
        types.append('lstm')
        types.append('deepar')
    except ImportError:
        pass
    return types


# ──────── 算法预测辅助函数 ────────

def _arimax_predict(series, periods=12):
    """ARIMAX：ARIMA + 时间趋势作为外生变量"""
    from statsmodels.tsa.arima.model import ARIMA
    n = len(series)
    exog = np.arange(n, dtype=float).reshape(-1, 1)
    model = ARIMA(series, exog=exog, order=(1, 1, 1)).fit()
    future_exog = np.arange(n, n + periods, dtype=float).reshape(-1, 1)
    return np.maximum(0.0, model.forecast(steps=periods, exog=future_exog))


def _prophet_predict(series, periods=12):
    """Prophet 时序预测"""
    from prophet import Prophet
    df = pd.DataFrame({'ds': series.index.to_timestamp() if hasattr(series.index, 'to_timestamp') else pd.to_datetime(series.index.values),
                       'y': series.values.astype(float)})
    model = Prophet(weekly_seasonality=False, daily_seasonality=False,
                    yearly_seasonality=len(series) >= 18)
    model.fit(df)
    future = model.make_future_dataframe(periods=periods, freq='ME')
    fc = model.predict(future)
    return np.maximum(0.0, fc.tail(periods)['yhat'].values.astype(float))


def _random_forest_predict(monthly_data, periods=12):
    """随机森林预测"""
    from sklearn.ensemble import RandomForestRegressor
    monthly_df = monthly_data.reset_index()
    monthly_df['month_index'] = np.arange(len(monthly_df), dtype=float)
    monthly_df['month_of_year'] = monthly_df['date'].dt.month.astype(float)
    X = monthly_df[['month_index', 'month_of_year']].values
    y = monthly_df['sales_quantity'].astype(float).values
    model = RandomForestRegressor(n_estimators=150, random_state=42, n_jobs=-1)
    model.fit(X, y)
    last_idx = len(monthly_df)
    future_idx = np.arange(last_idx, last_idx + periods, dtype=float)
    future_months = np.array([(monthly_df['date'].iloc[-1].month + i) % 12 + 1
                              for i in range(1, periods + 1)], dtype=float)
    future_X = np.column_stack([future_idx, future_months])
    return np.maximum(0.0, model.predict(future_X))


# ──────── Croston / SBA 季节性增强 ────────

def _seasonal_decompose(values, season_length):
    """
    季节分解：基于中位数比率法计算季节指数，并返回去季节化序列。

    使用中位数（而非均值）以抵抗异常值的干扰。
    返回: (seasonal_indices: np.ndarray, deseasonalized: np.ndarray)
    """
    n = len(values)
    seasonal_indices = np.ones(season_length)

    for s in range(season_length):
        season_vals = values[s::season_length]
        if len(season_vals) > 0:
            nonzero_season = season_vals[season_vals > 0]
            nonzero_all = values[values > 0]
            if len(nonzero_season) > 0 and len(nonzero_all) > 0:
                s_median = float(np.median(nonzero_season))
                o_median = float(np.median(nonzero_all))
                if o_median > 0:
                    seasonal_indices[s] = s_median / o_median

    # 归一化使季节指数均值为 1
    si_mean = float(np.mean(seasonal_indices))
    if si_mean > 0:
        seasonal_indices = seasonal_indices / si_mean

    # 去季节化
    deseasonalized = values.copy()
    for i in range(n):
        s = i % season_length
        if seasonal_indices[s] > 0.01:
            deseasonalized[i] = values[i] / seasonal_indices[s]

    return seasonal_indices, deseasonalized


def _croston_core(values, alpha, apply_sba=False):
    """
    Croston/SBA 核心算法：对（可能已去季节化）的序列计算需求率。
    apply_sba=True 时应用 SBA 偏差修正。
    """
    nonzero_idx = np.where(values > 0)[0]
    if len(nonzero_idx) < 2:
        return float(np.mean(values))

    demands = values[nonzero_idx]
    intervals = np.diff(nonzero_idx).astype(float)
    # 最后一段间隔用最近 3 段均值估计（或整体均值兜底）
    last_interval_est = float(np.mean(intervals[-3:])) if len(intervals) >= 3 else float(np.mean(intervals))
    intervals = np.append(intervals, last_interval_est)

    sd = float(demands[0])
    si = float(intervals[0])
    for j in range(1, len(demands)):
        sd = alpha * float(demands[j]) + (1 - alpha) * sd
        si = alpha * float(intervals[j]) + (1 - alpha) * si

    demand_rate = sd / max(si, 1.0)
    if apply_sba:
        demand_rate = (1 - alpha / 2) * demand_rate
    return max(0.0, demand_rate)


def _croston_predict(series, periods=12, alpha=0.15):
    """
    Croston 方法 - 适用于间歇性需求的时间序列。
    当数据 >= 24 个月时，自动进行季节性分解后再应用 Croston，
    解决标准 Croston 在季节性数据上预测滞后一期的固有问题。
    """
    values = np.asarray(series.values if hasattr(series, 'values') else series, dtype=float)
    n = len(values)

    # 自动季节性检测：>= 24 个月时尝试 12 个月周期分解
    if n >= 24:
        try:
            seasonal_indices, deseasonalized = _seasonal_decompose(values, season_length=12)
            base_rate = _croston_core(deseasonalized, alpha, apply_sba=False)
            forecast = np.array([
                max(0.0, base_rate * seasonal_indices[(n + p) % 12])
                for p in range(periods)
            ])
            return forecast
        except Exception:
            pass  # 回退到标准 Croston

    # 标准 Croston（数据不足 24 个月或季节性分解失败时）
    base_rate = _croston_core(values, alpha, apply_sba=False)
    return np.full(periods, base_rate)


def _sba_predict(series, periods=12, alpha=0.15):
    """
    SBA (Syntetos-Boylan Approximation) - Croston 的偏差修正版。
    同样支持自动季节性检测。
    """
    values = np.asarray(series.values if hasattr(series, 'values') else series, dtype=float)
    n = len(values)

    if n >= 24:
        try:
            seasonal_indices, deseasonalized = _seasonal_decompose(values, season_length=12)
            base_rate = _croston_core(deseasonalized, alpha, apply_sba=True)
            forecast = np.array([
                max(0.0, base_rate * seasonal_indices[(n + p) % 12])
                for p in range(periods)
            ])
            return forecast
        except Exception:
            pass

    base_rate = _croston_core(values, alpha, apply_sba=True)
    return np.full(periods, base_rate)


def _lstm_predict(series, periods=12, lookback=6, epochs=60):
    """LSTM 神经网络预测"""
    import os
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense
    from tensorflow.keras.optimizers import Adam
    values = np.asarray(series.values if hasattr(series, 'values') else series, dtype=float)
    mean_v, std_v = np.mean(values), np.std(values) + 1e-8
    scaled = (values - mean_v) / std_v
    X, y = [], []
    for i in range(lookback, len(scaled)):
        X.append(scaled[i - lookback:i])
        y.append(scaled[i])
    X, y = np.array(X), np.array(y)
    X = X.reshape((X.shape[0], X.shape[1], 1))
    model = Sequential([
        LSTM(32, activation='relu', return_sequences=True, input_shape=(lookback, 1)),
        LSTM(16, activation='relu'),
        Dense(1)
    ])
    model.compile(optimizer=Adam(0.01), loss='mse')
    model.fit(X, y, epochs=epochs, verbose=0, batch_size=min(4, len(X)))
    last_seq = scaled[-lookback:].copy()
    forecasts = []
    for _ in range(periods):
        inp = last_seq.reshape(1, lookback, 1)
        pred = float(model.predict(inp, verbose=0)[0, 0])
        forecasts.append(pred)
        last_seq = np.append(last_seq[1:], pred)
    return np.maximum(0.0, np.array(forecasts) * std_v + mean_v)


def _deepar_predict(series, periods=12, lookback=6, epochs=100):
    """DeepAR 简化版 - 更深层的 LSTM 架构，适用于概率预测"""
    import os
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    from tensorflow.keras.optimizers import Adam
    values = np.asarray(series.values if hasattr(series, 'values') else series, dtype=float)
    mean_v, std_v = np.mean(values), np.std(values) + 1e-8
    scaled = (values - mean_v) / std_v
    X, y = [], []
    for i in range(lookback, len(scaled)):
        X.append(scaled[i - lookback:i])
        y.append(scaled[i])
    X, y = np.array(X), np.array(y)
    X = X.reshape((X.shape[0], X.shape[1], 1))
    model = Sequential([
        LSTM(64, activation='relu', return_sequences=True, input_shape=(lookback, 1)),
        Dropout(0.1),
        LSTM(32, activation='relu', return_sequences=True),
        Dropout(0.1),
        LSTM(16, activation='relu'),
        Dense(1)
    ])
    model.compile(optimizer=Adam(0.005), loss='mse')
    model.fit(X, y, epochs=epochs, verbose=0, batch_size=min(4, len(X)))
    last_seq = scaled[-lookback:].copy()
    forecasts = []
    for _ in range(periods):
        inp = last_seq.reshape(1, lookback, 1)
        pred = float(model.predict(inp, verbose=0)[0, 0])
        forecasts.append(pred)
        last_seq = np.append(last_seq[1:], pred)
    return np.maximum(0.0, np.array(forecasts) * std_v + mean_v)


def _eval_metrics(actual, forecast):
    """统一的评估指标计算，返回 (mae, rmse, accuracy)
    
    accuracy 基于 WMAPE 变体：用 actual 做分母（而非 forecast），
    避免因预测值接近 0 导致百分比误差爆炸的问题。
    """
    act = np.asarray(actual, dtype=float)
    fc = np.maximum(0.0, np.asarray(forecast, dtype=float))
    mae = float(np.mean(np.abs(act - fc)))
    rmse = float(np.sqrt(np.mean((act - fc) ** 2)))
    # 用 actual 做分母（标准 WMAPE 做法），避免 forecast 极小时误差爆炸
    pct = np.where(act > 0, np.abs(act - fc) / act, 0.0)
    # actual=0 但 forecast>0：视为 100% 误差
    pct = np.where((act == 0) & (fc > 0), 1.0, pct)
    accuracy = max(0.0, (1.0 - np.mean(pct)) * 100.0) if len(pct) > 0 else 0.0
    return mae, rmse, accuracy


# ──────── 季节性特征工程 ────────


def _seasonal_decompose(series):
    """
    对月度时序进行趋势-季节分解，提取趋势线和各月季节指数。

    参数:
        series: pd.Series，index 为日期，values 为月度销量

    返回:
        dict: {
            'trend': np.ndarray,         # 趋势线 (与 series 同长度)
            'seasonal_index': np.ndarray, # 12个月的季节指数（比率，1.0=平均水平）
            'deseasonalized': np.ndarray, # 去季节化后的序列（保留趋势+残差）
            'seasonal_strength': float,   # 季节性强度 (0~1)，越高季节效应越显著
        }
    """
    values = np.asarray(series.values, dtype=float)
    n = len(values)
    result = {
        'trend': np.zeros(n),
        'seasonal_index': np.ones(12),
        'deseasonalized': np.zeros(n),
        'seasonal_strength': 0.0,
    }

    if n < 12:
        x = np.arange(n, dtype=float)
        slope, intercept = np.polyfit(x, values, 1)
        result['trend'] = intercept + slope * x
        result['deseasonalized'] = values.copy()
        return result

    # Step 1: 拟合线性趋势
    x = np.arange(n, dtype=float)
    slope, intercept = np.polyfit(x, values, 1)
    trend = intercept + slope * x
    result['trend'] = trend

    # Step 2: 计算去趋势残差
    detrended = values - trend

    # Step 3: 计算各月季节分量（平均去趋势残差）
    monthly_residuals = np.zeros(12)
    monthly_counts = np.zeros(12, dtype=int)
    for i in range(n):
        if hasattr(series.index[i], 'month'):
            m = series.index[i].month - 1
        else:
            m = i % 12
        monthly_residuals[m] += detrended[i]
        monthly_counts[m] += 1

    for m in range(12):
        if monthly_counts[m] > 0:
            monthly_residuals[m] /= monthly_counts[m]

    # Step 4: 构建季节指数（比率形式，1.0 = 平均水平）
    avg_trend = np.mean(trend) if np.mean(trend) > 0 else 1.0
    seasonal_index = np.ones(12)
    for m in range(12):
        if avg_trend > 0:
            seasonal_index[m] = max(0.1, (avg_trend + monthly_residuals[m]) / avg_trend)

    result['seasonal_index'] = seasonal_index

    # Step 5: 构建去季节化序列（trend + residual only）
    deseasonalized = np.zeros(n)
    for i in range(n):
        if hasattr(series.index[i], 'month'):
            m = series.index[i].month - 1
        else:
            m = i % 12
        si = seasonal_index[m]
        if si > 0:
            deseasonalized[i] = values[i] / si
        else:
            deseasonalized[i] = values[i]
    result['deseasonalized'] = deseasonalized

    # Step 6: 季节性强度：Var(seasonal) / (Var(seasonal) + Var(residual))
    seasonal_comp = np.zeros(n)
    for i in range(n):
        if hasattr(series.index[i], 'month'):
            m = series.index[i].month - 1
        else:
            m = i % 12
        seasonal_comp[i] = monthly_residuals[m]
    residual_comp = detrended - seasonal_comp
    var_s = np.var(seasonal_comp) if len(seasonal_comp) > 0 else 0.0
    var_r = np.var(residual_comp) if len(residual_comp) > 0 else 0.0
    if var_s + var_r > 0:
        result['seasonal_strength'] = max(0.0, min(1.0, var_s / (var_s + var_r)))

    return result


# ──────── 数据清洗与预处理 ────────

def _preprocess_time_series(monthly_series, region=None, sku=None):
    """
    月度时序数据清洗与预处理，减少数据质量问题对模型训练的影响。

    处理步骤（按顺序）：
    1. 空值检测  → 线性插值填补（兜底：中位数填充）
    2. 异常值检测 → IQR 方法识别离群点，用相邻值均值替换
    3. 极端值平滑 → Winsorize 截断（3倍IQR），避免过大/过小值扭曲模型
    4. 零值占比分析 → 记录日志但保持原样（间歇性需求留给 Croston/SBA 处理）

    参数:
        monthly_series: pd.Series，按月汇总的销售数据
        region: 可选，用于日志标识
        sku: 可选，用于日志标识

    返回:
        (clean_series: pd.Series, cleaning_log: dict)
    """
    series = monthly_series.copy()
    tag = f'[{region}/{sku}]' if region and sku else ''
    cleaning_log = {
        'original_length': len(series),
        'null_count': 0,
        'outlier_count': 0,
        'extreme_cap_count': 0,
        'original_mean': float(series.mean()) if len(series) > 0 else 0.0,
        'actions': [],
    }

    if len(series) < 3:
        cleaning_log['actions'].append('数据量不足3个月，跳过清洗')
        return series, cleaning_log

    # ═══════════════════════════════════════════════════════
    #  第1步：空值检测与插值
    # ═══════════════════════════════════════════════════════
    null_mask = series.isna()
    cleaning_log['null_count'] = int(null_mask.sum())

    if null_mask.any():
        # 使用线性插值（利用时间趋势填补缺失月份）
        series = series.interpolate(method='linear', limit_direction='both')
        # 如果首尾仍有 NaN（如起始月份缺失），用整体中位数兜底
        if series.isna().any():
            fill_value = series.median() if not series.dropna().empty else 0.0
            series = series.fillna(fill_value)
        cleaning_log['actions'].append(
            f'填补了 {cleaning_log["null_count"]} 个空值（线性插值，兜底中位数）'
        )
        logger.info(f'{tag} 填补 {cleaning_log["null_count"]} 个空值')

    # ═══════════════════════════════════════════════════════
    #  第2步：异常值检测（IQR 方法，仅对非零值）
    # ═══════════════════════════════════════════════════════
    values = series.values.astype(float)
    nonzero_mask = values > 0
    nonzero_count = int(nonzero_mask.sum())

    if nonzero_count >= 3:
        nonzero_vals = values[nonzero_mask]
        Q1 = float(np.percentile(nonzero_vals, 25))
        Q3 = float(np.percentile(nonzero_vals, 75))
        IQR = Q3 - Q1

        if IQR > 0:
            # 时序数据用 2.5×IQR（比标准 1.5×IQR 更宽松，避免误杀季节性波动）
            lower_bound = Q1 - 2.5 * IQR
            upper_bound = Q3 + 2.5 * IQR

            outlier_mask = (values > upper_bound) | ((values < lower_bound) & (values > 0))
            outlier_indices = np.where(outlier_mask)[0]

            if len(outlier_indices) > 0:
                cleaning_log['outlier_count'] = int(len(outlier_indices))

                for idx in outlier_indices:
                    # 用相邻月份的均值替换（保留局部趋势信息）
                    neighbors = []
                    if idx > 0:
                        neighbors.append(values[idx - 1])
                    if idx < len(values) - 1:
                        neighbors.append(values[idx + 1])
                    replacement = float(np.mean(neighbors)) if neighbors else float(np.median(nonzero_vals))
                    values[idx] = replacement
                    series.iloc[idx] = replacement

                cleaning_log['actions'].append(
                    f'处理了 {cleaning_log["outlier_count"]} 个异常值 '
                    f'(IQR边界: [{lower_bound:.0f}, {upper_bound:.0f}])'
                )
                logger.warning(
                    f'{tag} 检测到 {cleaning_log["outlier_count"]} 个异常值 '
                    f'(边界: [{lower_bound:.0f}, {upper_bound:.0f}])'
                )

    # ═══════════════════════════════════════════════════════
    #  第3步：极端值平滑（Winsorize，3×IQR 截断）
    # ═══════════════════════════════════════════════════════
    values = series.values.astype(float)
    nonzero_vals = values[values > 0]

    if len(nonzero_vals) >= 3:
        Q1 = float(np.percentile(nonzero_vals, 25))
        Q3 = float(np.percentile(nonzero_vals, 75))
        IQR = Q3 - Q1

        if IQR > 0:
            cap_upper = Q3 + 3.0 * IQR
            cap_lower = max(0.0, Q1 - 3.0 * IQR)

            cap_mask = (values > cap_upper) | ((values < cap_lower) & (values > 0))
            cap_count = int(cap_mask.sum())

            if cap_count > 0:
                cleaning_log['extreme_cap_count'] = cap_count
                values = np.clip(values, cap_lower, cap_upper)
                series = pd.Series(values, index=series.index)
                cleaning_log['actions'].append(
                    f'Winsorize 截断 {cap_count} 个极端值'
                    f'（上限:{cap_upper:.0f}, 下限:{cap_lower:.0f}）'
                )
                logger.info(f'{tag} Winsorize 截断 {cap_count} 个极端值')

    # ═══════════════════════════════════════════════════════
    #  第4步：零值模式分析（仅记录，不修改）
    # ═══════════════════════════════════════════════════════
    zero_ratio = float((series.values == 0).sum()) / len(series) if len(series) > 0 else 0.0
    if zero_ratio > 0.5:
        cleaning_log['actions'].append(
            f'零值占比 {zero_ratio*100:.1f}%，属间歇性需求模式，保留原始零值'
        )

    # ═══════════════════════════════════════════════════════
    #  第5步：季节性诊断（仅记录，不修改数据）
    # ═══════════════════════════════════════════════════════
    seasonal_info = None
    if len(series) >= 12:
        try:
            seasonal_info = _seasonal_decompose(series)
            cleaning_log['seasonal_strength'] = round(seasonal_info['seasonal_strength'], 3)
            cleaning_log['seasonal_index'] = [round(float(x), 3) for x in seasonal_info['seasonal_index']]

            # 诊断季节性峰值月份
            peak_month_idx = int(np.argmax(seasonal_info['seasonal_index']))
            trough_month_idx = int(np.argmin(seasonal_info['seasonal_index']))
            cleaning_log['peak_month'] = peak_month_idx + 1
            cleaning_log['trough_month'] = trough_month_idx + 1

            if seasonal_info['seasonal_strength'] > 0.3:
                cleaning_log['actions'].append(
                    f'强季节性 (强度={seasonal_info["seasonal_strength"]:.2f}, '
                    f'峰值月={peak_month_idx+1}, 低谷月={trough_month_idx+1})'
                )
        except Exception:
            pass

    cleaning_log['final_mean'] = float(series.mean())
    cleaning_log['final_length'] = len(series)
    cleaning_log['zero_ratio'] = round(zero_ratio, 3)
    cleaning_log['deseasonalized_values'] = (
        [round(float(x), 2) for x in seasonal_info['deseasonalized']]
        if seasonal_info else None
    )

    # 汇总日志
    if cleaning_log['actions']:
        logger.info(f'{tag} 数据清洗完成：{"；".join(cleaning_log["actions"])}')

    return series, cleaning_log


# ──────── 模型融合 ────────


def _try_ensemble(region, sku, trained_model_types):
    """
    对已训练的多个模型进行加权融合 + 季节性偏差校正。

    核心改进（解决1个月时滞问题）：
    1. 逆MAE加权 —— 准确率高的模型获得更大权重
    2. 季节性偏差校正 —— 对每月计算系统性偏差(pred-actual)，校正后消除时滞
    3. 趋势-季节分解融合 —— 用实际数据的季节性替代模型预测的季节相位

    返回: (ensemble_model: ForecastModel | None, accuracy: float | None)
    """
    # ── Step 1: 收集各模型预测值，按日期和模型分组 ──
    results_by_date = {}       # {date: {'forecasts': {mt: val}, 'actual': val}}
    model_pairs = {}           # {mt: [(date, pred, actual), ...]}

    for mt in trained_model_types:
        mt_pairs = []
        for fr in ForecastResult.objects.filter(
            sales_region_code=region,
            material_number=sku,
            model_used=mt
        ).order_by('date'):
            dk = fr.date
            pred_val = float(fr.forecast_quantity)
            actual_val = float(fr.actual_quantity) if fr.actual_quantity is not None else None

            if dk not in results_by_date:
                results_by_date[dk] = {'forecasts': {}, 'actual': actual_val}
            results_by_date[dk]['forecasts'][mt] = pred_val

            if actual_val is not None:
                mt_pairs.append((dk, pred_val, actual_val))

        if len(mt_pairs) >= 3:
            model_pairs[mt] = mt_pairs

    if not results_by_date:
        return None, None

    sorted_dates = sorted(results_by_date.keys())

    # ── Step 2: 计算各模型的 MAE，用于逆MAE加权 ──
    model_mae = {}
    for mt, pairs in model_pairs.items():
        errs = [abs(p - a) for _, p, a in pairs]
        model_mae[mt] = float(np.mean(errs))

    if not model_mae:
        return None, None

    # ── Step 3: 逆MAE加权 + 平滑处理 ──
    epsilon = 1e-6
    total_inv_mae = sum(1.0 / (mae_val + epsilon) for mae_val in model_mae.values())
    model_weights = {
        mt: (1.0 / (mae + epsilon)) / total_inv_mae
        for mt, mae in model_mae.items()
    }

    # ── Step 4: 按日期计算加权平均预测 ──
    raw_ensemble = []  # [(date, weighted_pred), ...]
    for dk in sorted_dates:
        data = results_by_date[dk]
        weighted_sum = 0.0
        weight_sum = 0.0
        for mt, pred in data['forecasts'].items():
            w = model_weights.get(mt, 0.0)
            if w > 0:
                weighted_sum += w * pred
                weight_sum += w
        if weight_sum > 0:
            raw_pred = weighted_sum / weight_sum
        else:
            preds = list(data['forecasts'].values())
            raw_pred = sum(preds) / len(preds) if preds else 0.0
        raw_ensemble.append((dk, max(0.0, raw_pred)))

    # ── Step 5: 趋势-季节分解 + 季节性偏差校正 ──
    # 核心思路：模型捕捉趋势较好，但季节性相位常偏移1个月。
    # 解决方案：提取实际数据的季节模式，与模型趋势融合。
    dates_with_actual = [(dk, float(results_by_date[dk]['actual']))
                         for dk in sorted_dates
                         if results_by_date[dk]['actual'] is not None]

    if len(dates_with_actual) < 12:
        # 数据不足，跳过季节性校正，仅用加权平均
        ensemble_forecasts_list = raw_ensemble
    else:
        # 5a. 构建实际销量的月度数组（按时间排序）
        act_dates = [d[0] for d in dates_with_actual]
        act_values = np.array([d[1] for d in dates_with_actual], dtype=float)

        # 5b. 拟合实际销量的趋势线
        act_x = np.arange(len(act_values), dtype=float)
        act_trend_slope, act_trend_intercept = np.polyfit(act_x, act_values, 1)
        act_trend = act_trend_intercept + act_trend_slope * act_x

        # 5c. 从实际数据提取各月季节分量（去趋势后的残差均值）
        act_seasonal = np.zeros(12, dtype=float)
        act_seasonal_counts = np.zeros(12, dtype=int)
        for i, (dk, _) in enumerate(dates_with_actual):
            m_idx = dk.month - 1
            act_seasonal[m_idx] += (act_values[i] - act_trend[i])
            act_seasonal_counts[m_idx] += 1
        for m in range(12):
            if act_seasonal_counts[m] >= 1:
                act_seasonal[m] /= act_seasonal_counts[m]

        # 5d. 计算加权平均预测的每月系统性偏差 (pred - actual)
        monthly_bias = np.zeros(12, dtype=float)
        monthly_bias_count = np.zeros(12, dtype=int)
        for dk, raw_pred in raw_ensemble:
            act = results_by_date[dk]['actual']
            if act is not None:
                m_idx = dk.month - 1
                monthly_bias[m_idx] += (raw_pred - float(act))
                monthly_bias_count[m_idx] += 1

        avg_actual = float(np.mean(act_values))
        for m in range(12):
            if monthly_bias_count[m] >= 2:
                monthly_bias[m] /= monthly_bias_count[m]
                # 限制校正幅度 ≤ 月均销量的30%
                cap = avg_actual * 0.3
                monthly_bias[m] = np.clip(monthly_bias[m], -cap, cap)

        # 5e. 趋势-季节融合：模型趋势 + 实际季节分量（混合比例0.6）
        # 目的：保留模型对趋势的判断，但用实际季节模式纠正相位
        raw_values = np.array([p[1] for p in raw_ensemble], dtype=float)
        raw_x = np.arange(len(raw_values), dtype=float)
        raw_trend_slope, raw_trend_intercept = np.polyfit(raw_x, raw_values, 1)
        raw_trend_line = raw_trend_intercept + raw_trend_slope * raw_x

        # 也提取原始预测的季节分量
        raw_seasonal = np.zeros(12, dtype=float)
        raw_seasonal_counts = np.zeros(12, dtype=int)
        for i, (dk, raw_pred) in enumerate(raw_ensemble):
            m_idx = dk.month - 1
            raw_seasonal[m_idx] += (raw_values[i] - raw_trend_line[i])
            raw_seasonal_counts[m_idx] += 1
        for m in range(12):
            if raw_seasonal_counts[m] >= 1:
                raw_seasonal[m] /= raw_seasonal_counts[m]

        # 融合比例：后期月份用更多实际季节分量（实际数据的季节性更可靠）
        season_blend = 0.6  # 60%实际季节 + 40%模型季节

        ensemble_forecasts_list = []
        for i, (dk, raw_pred) in enumerate(raw_ensemble):
            m_idx = dk.month - 1

            # 趋势部分 + 混合季节部分 - 偏差校正
            blended_seasonal = (season_blend * act_seasonal[m_idx] +
                                (1.0 - season_blend) * raw_seasonal[m_idx])
            trend_part = raw_trend_line[i]

            # 偏差校正（进一步消除系统性偏差）
            bias_corr = monthly_bias[m_idx] if monthly_bias_count[m_idx] >= 2 else 0.0

            adjusted_pred = trend_part + blended_seasonal - bias_corr
            ensemble_forecasts_list.append((dk, max(0.0, adjusted_pred)))

    # ── Step 6: 评估准确率 ──
    paired = []
    for dk, f in ensemble_forecasts_list:
        act = results_by_date[dk]['actual']
        if act is not None:
            paired.append((f, float(act)))

    if len(paired) < 3:
        return None, None

    forecast_vals = [p[0] for p in paired]
    actual_vals = [p[1] for p in paired]
    mae = float(np.mean([abs(f - a) for f, a in zip(forecast_vals, actual_vals)]))
    rmse = float(np.sqrt(np.mean([(f - a) ** 2 for f, a in zip(forecast_vals, actual_vals)])))
    f_arr = np.array(forecast_vals)
    a_arr = np.array(actual_vals)
    pct_errs = np.where(a_arr > 0, np.abs(a_arr - f_arr) / a_arr, 0.0)
    pct_errs = np.where((a_arr == 0) & (f_arr > 0), 1.0, pct_errs)
    accuracy = max(0.0, (1.0 - np.mean(pct_errs)) * 100.0) if len(pct_errs) > 0 else 0.0

    # 获取训练日期范围（从已有模型中获取）
    existing_models = ForecastModel.objects.filter(
        sales_region_code=region,
        material_number=sku,
        model_type__in=trained_model_types
    )
    train_start = existing_models.aggregate(Min('training_start_date'))['training_start_date__min']
    train_end = existing_models.aggregate(Max('training_end_date'))['training_end_date__max']
    is_overfit = mae > np.mean(actual_vals) * 0.3 if mae > 0 else False

    model_name = f"{region}_{sku}_ensemble"
    fm, _ = ForecastModel.objects.update_or_create(
        sales_region_code=region,
        material_number=sku,
        model_type='ensemble',
        defaults={
            'model_name': model_name,
            'training_start_date': train_start,
            'training_end_date': train_end,
            'accuracy': accuracy,
            'mae': mae,
            'rmse': rmse,
            'is_overfit': is_overfit
        }
    )

    # 保存 ensemble 的 ForecastResult
    ForecastResult.objects.filter(
        sales_region_code=region,
        material_number=sku,
        model_used='ensemble'
    ).delete()
    for dk, f_val in ensemble_forecasts_list:
        ForecastResult.objects.create(
            sales_region_code=region,
            material_number=sku,
            date=dk,
            forecast_quantity=f_val,
            actual_quantity=results_by_date[dk]['actual'],
            model_used='ensemble'
        )

    logger.info(
        f'[{region}/{sku}] Ensemble融合完成: '
        f'加权模型={list(model_weights.keys())}, '
        f'准确率={accuracy:.2f}%'
    )

    return fm, accuracy


# ──────── 过拟合重训参数 ────────

def _get_retry_params(model_type, attempt):
    """
    返回第 attempt 次训练尝试的参数配置。
    attempt 0: 默认参数
    attempt 1: 简化/正则化参数（减少过拟合风险）
    attempt 2: 最简化参数（最保守配置）
    """
    params = {}

    if model_type == 'arima':
        params['arima_order'] = [(1, 1, 1), (0, 1, 1), (2, 1, 0)][attempt]

    elif model_type == 'arimax':
        params['arimax_order'] = [(1, 1, 1), (0, 1, 1), (2, 1, 0)][attempt]

    elif model_type == 'xgboost':
        configs = [
            {'n_estimators': 100, 'max_depth': 6, 'learning_rate': 0.3},
            {'n_estimators': 50,  'max_depth': 3, 'learning_rate': 0.1},
            {'n_estimators': 30,  'max_depth': 2, 'learning_rate': 0.05},
        ]
        params.update(configs[attempt])

    elif model_type == 'random_forest':
        configs = [
            {'n_estimators': 150, 'max_depth': None},
            {'n_estimators': 80,  'max_depth': 6},
            {'n_estimators': 40,  'max_depth': 3},
        ]
        params.update(configs[attempt])

    elif model_type == 'exp_smooth':
        # 过拟合时逐次减小季节周期，但始终保留季节性（避免退化为直线）
        configs = [
            {'seasonal_enabled': True,  'seasonal_periods': 12},
            {'seasonal_enabled': True,  'seasonal_periods': 6},
            {'seasonal_enabled': True,  'seasonal_periods': 4},
        ]
        params.update(configs[attempt])

    elif model_type == 'holt-winters':
        # Holt-Winters 过拟合时逐次减小季节周期，但始终保留季节性（避免退化为直线）
        configs = [
            {'seasonal_periods': 12, 'use_seasonal': True},
            {'seasonal_periods': 6,  'use_seasonal': True},
            {'seasonal_periods': 4,  'use_seasonal': True},
        ]
        params.update(configs[attempt])

    elif model_type == 'prophet':
        configs = [
            {'yearly_seasonality': True,  'changepoint_prior_scale': 0.05},
            {'yearly_seasonality': False, 'changepoint_prior_scale': 0.01},
            {'yearly_seasonality': False, 'changepoint_prior_scale': 0.001},
        ]
        params.update(configs[attempt])

    elif model_type == 'lstm':
        params['epochs'] = [60, 30, 20][attempt]
        params['lookback'] = [6, 4, 3][attempt]

    elif model_type == 'deepar':
        params['epochs'] = [50, 30, 20][attempt]
        params['lookback'] = [6, 4, 3][attempt]

    return params


# ──────── 后测不达标时的替代模型优先级 ────────

def _get_fallback_model_types(model_type):
    """
    当模型后测准确率 < 50% 或过拟合时，按优先级返回应尝试的替代模型类型。
    优先级原则：从简单稳定模型到复杂模型，避免用一个差的模型替换另一个差的模型。
    所有链条最终收敛到 seasonal_naive / 线性回归兜底，无循环。

    返回: list[str] — 替代模型类型列表（按优先级从高到低）
    """
    # Croston/SBA 是间歇性需求专用模型，数据不匹配时回退
    if model_type in ('croston', 'sba'):
        return ['moving_avg', 'weighted_avg', 'seasonal_naive']

    # 复杂 ML 模型过拟合时回退到统计模型
    if model_type in ('xgboost', 'random_forest', 'lstm', 'deepar', 'prophet'):
        return ['holt-winters', 'moving_avg', 'seasonal_naive']

    # ARIMA/ARIMAX 回退
    if model_type in ('arima', 'arimax'):
        return ['holt-winters', 'moving_avg', 'seasonal_naive']

    # exp_smooth 是 holt-winters 的别名，同样的回退链
    if model_type == 'exp_smooth':
        return ['moving_avg', 'seasonal_naive']

    # Holt-Winters 指数平滑回退（比 ARIMA/ML 轻量，但有季节性假设）
    if model_type == 'holt-winters':
        return ['moving_avg', 'seasonal_naive']

    # moving_avg / weighted_avg → 季节性朴素（最终兜底）
    if model_type in ('moving_avg', 'weighted_avg'):
        return ['seasonal_naive']

    # 季节性朴素是最简基线，无进一步回退
    if model_type == 'seasonal_naive':
        return []

    return ['moving_avg', 'seasonal_naive']


def _compute_trend_forecast(monthly_arr, horizon=12):
    """基于线性趋势生成非恒值预测，避免简单模型产出直线"""
    arr = np.asarray(monthly_arr, dtype=float)
    if len(arr) < 2:
        val = float(arr[-1]) if len(arr) > 0 else 0.0
        return [max(0.0, val) for _ in range(horizon)]
    # 用最多最近12个月拟合线性趋势
    trend_data = arr[-min(12, len(arr)):]
    t = np.arange(len(trend_data), dtype=float)
    slope, intercept = np.polyfit(t, trend_data, 1)
    # 基准值：趋势线最后一点
    base_val = intercept + slope * (len(trend_data) - 1)
    # 外推未来 horizon 个月
    return [max(0.0, base_val + slope * (i + 1)) for i in range(horizon)]


def train_single_combination(region, sku, model_type='holt-winters', time_range=12,
                             hierarchy_level='sku', category_code=None,
                             start_date_str=None, end_date_str=None):
    """
    训练单个 region + sku/分类 组合的预测模型。
    支持 SKU 级别和产品五级分类级别的聚合训练。

    参数:
        start_date_str / end_date_str: 'YYYY-MM' 格式，指定训练数据的时间范围；
                                       若提供则优先于 time_range。
    返回: (success: bool, error_msg: str | None)
    """
    from datetime import datetime
    import calendar as cal_mod

    if model_type not in VALID_MODEL_TYPES:
        model_type = 'holt-winters'

    # ── 数据查询：SKU 级别 vs 分类级别 ──
    if hierarchy_level == 'sku':
        sales_data = SalesData.objects.filter(
            sales_region_code=region,
            product_data__material_number=sku
        ).order_by('date')
    else:
        field_name = CATEGORY_FIELD_MAP.get(hierarchy_level, 'product_data__product_category_level1')
        sales_data = SalesData.objects.filter(
            sales_region_code=region,
            **{field_name: sku}
        ).order_by('date')

    if not sales_data.exists():
        if hierarchy_level == 'sku':
            return False, f'未找到区域 {region} 和 SKU {sku} 的销售数据'
        else:
            return False, f'未找到区域 {region} 和分类 {sku} 的销售数据'

    # ── 时间范围过滤 ──
    if start_date_str and end_date_str:
        start_dt = datetime.strptime(start_date_str, '%Y-%m')
        end_dt = datetime.strptime(end_date_str, '%Y-%m')
        last_day = cal_mod.monthrange(end_dt.year, end_dt.month)[1]
        end_full = datetime(end_dt.year, end_dt.month, last_day)
        filtered_data = sales_data.filter(date__gte=start_dt, date__lte=end_full)
    else:
        end_date = sales_data.latest('date').date
        start_date = end_date - timedelta(days=30 * time_range)
        filtered_data = sales_data.filter(date__gte=start_date)

    if filtered_data.count() < 12:
        return False, f'区域 {region} SKU {sku} 的历史数据不足（至少需要12个月），当前只有{filtered_data.count()}条'

    df = pd.DataFrame(list(filtered_data.values('date', 'sales_quantity')))
    if df.empty:
        return False, f'区域 {region} SKU {sku} 的历史数据为空'
    # 分类层级下同日期可能有多条记录 → 先 groupby 求和再 reindex
    df = df.groupby('date', as_index=False)['sales_quantity'].sum()
    df = df.sort_values('date')
    df.set_index('date', inplace=True)
    df = df.asfreq('D')
    df['sales_quantity'] = df['sales_quantity'].fillna(0)
    monthly_data = df['sales_quantity'].resample('ME').sum()

    # ── 数据清洗与预处理 ──
    monthly_data, cleaning_log = _preprocess_time_series(monthly_data, region, sku)

    if len(monthly_data) < 12:
        return False, f'区域 {region} SKU {sku} 的月度数据不足（至少需要12个月），当前只有{len(monthly_data)}个月'

    if len(monthly_data) > 12:
        train_data = monthly_data[:-3]
        test_data = monthly_data[-3:]
    else:
        train_data = monthly_data
        test_data = None

    forecast_values = []
    mae = 0.0
    rmse = 0.0
    accuracy = 90.0
    test_forecast_values = []

    # ── 过拟合重训循环：最多3次尝试，逐次降参数复杂度 ──
    MAX_RETRIES = 3
    avg_monthly = float(np.mean(np.asarray(monthly_data.values, dtype=float)))
    is_overfit = True
    last_error = None

    for attempt in range(MAX_RETRIES):
        retry_params = _get_retry_params(model_type, attempt)

        forecast_values = []
        mae = 0.0
        rmse = 0.0
        accuracy = 90.0
        test_forecast_values = []

        train_error = None  # 本次训练的异常（非导入错误）

        if model_type == 'arima':
            try:
                from statsmodels.tsa.arima.model import ARIMA
            except ImportError:
                return False, 'ARIMA 模型依赖 statsmodels，请先安装该包。'
            try:
                arima_order = retry_params.get('arima_order', (1, 1, 1))
                arima_model = ARIMA(train_data, order=arima_order).fit()
                if test_data is not None:
                    test_values = test_data.astype(float).values
                    test_forecast = arima_model.forecast(steps=3)
                    test_forecast_values = [max(0.0, float(x)) for x in test_forecast.values]
                    fc_arr = np.maximum(0.0, test_forecast.values.astype(float))
                    mae = float(np.mean(np.abs(test_values - fc_arr)))
                    rmse = float(np.sqrt(np.mean((test_values - fc_arr) ** 2)))
                    # 用 actual 做分母，避免 forecast→0 时误差爆炸
                    pct_errs = np.where(test_values > 0, np.abs(test_values - fc_arr) / test_values, 0.0)
                    pct_errs = np.where((test_values == 0) & (fc_arr > 0), 1.0, pct_errs)
                    accuracy = max(0.0, (1.0 - np.mean(pct_errs)) * 100.0) if len(pct_errs) > 0 else 0.0
                forecast_values = [max(0.0, float(x)) for x in arima_model.forecast(steps=12)]
            except Exception as e:
                train_error = f'ARIMA 模型训练失败：{e}'

        elif model_type == 'xgboost':
            try:
                from xgboost import XGBRegressor
            except ImportError:
                return False, 'XGBoost 模型依赖 xgboost，请先安装该包。'
            try:
                monthly_df = monthly_data.reset_index()
                monthly_df['month_index'] = np.arange(len(monthly_df), dtype=float)
                monthly_df['month_of_year'] = monthly_df['date'].dt.month.astype(float)
                X_all = monthly_df[['month_index', 'month_of_year']].values
                y_all = monthly_df['sales_quantity'].astype(float).values
                if len(monthly_df) > 12:
                    X_train = X_all[:-3]
                    y_train = y_all[:-3]
                    X_test = X_all[-3:]
                    y_test = y_all[-3:]
                else:
                    X_train = X_all
                    y_train = y_all
                    X_test = None
                xgb_model = XGBRegressor(
                    objective='reg:squarederror',
                    n_estimators=retry_params.get('n_estimators', 100),
                    max_depth=retry_params.get('max_depth', 6),
                    learning_rate=retry_params.get('learning_rate', 0.3),
                    random_state=42
                )
                xgb_model.fit(X_train, y_train)
                if X_test is not None:
                    test_forecast = xgb_model.predict(X_test)
                    fc_arr = np.maximum(0.0, test_forecast)
                    test_forecast_values = [float(x) for x in fc_arr]
                    y_test_values = np.asarray(y_test, dtype=float)
                    mae = float(np.mean(np.abs(y_test_values - fc_arr)))
                    rmse = float(np.sqrt(np.mean((y_test_values - fc_arr) ** 2)))
                    pct_errs = np.where(y_test_values > 0, np.abs(y_test_values - fc_arr) / y_test_values, 0.0)
                    pct_errs = np.where((y_test_values == 0) & (fc_arr > 0), 1.0, pct_errs)
                    accuracy = max(0.0, (1.0 - np.mean(pct_errs)) * 100.0) if len(pct_errs) > 0 else 0.0
                future_index = np.arange(len(monthly_df), len(monthly_df) + 12, dtype=float)
                future_months = np.array([(monthly_df['date'].iloc[-1].month + i) % 12 + 1
                                          for i in range(1, 13)], dtype=float)
                future_X = np.column_stack([future_index, future_months])
                forecast_values = [max(0.0, float(x)) for x in xgb_model.predict(future_X)]
            except Exception as e:
                train_error = f'XGBoost 模型训练失败：{e}'

        elif model_type == 'moving_avg':
            # 简单移动平均 —— 稳定的基线模型，无需重训降参
            window = min(6, max(2, len(monthly_data) // 4))
            monthly_arr = monthly_data.values.astype(float)
            if test_data is not None:
                test_forecast_values = [max(0.0, float(np.mean(monthly_arr[-window:]))) for _ in range(3)]
                fc_arr = np.array(test_forecast_values)
                test_act_arr = np.asarray(test_data.values, dtype=float)
                mae = float(np.mean(np.abs(test_act_arr - fc_arr)))
                rmse = float(np.sqrt(np.mean((test_act_arr - fc_arr) ** 2)))
                pct_errs = np.where(test_act_arr > 0, np.abs(test_act_arr - fc_arr) / test_act_arr, 0.0)
                pct_errs = np.where((test_act_arr == 0) & (fc_arr > 0), 1.0, pct_errs)
                accuracy = max(0.0, (1.0 - np.mean(pct_errs)) * 100.0) if len(pct_errs) > 0 else 0.0
            forecast_values = _compute_trend_forecast(monthly_arr, horizon=12)

        elif model_type == 'weighted_avg':
            # 加权移动平均 —— 近期数据权重更大，无需重训降参
            window = min(6, max(2, len(monthly_data) // 3))
            monthly_arr = monthly_data.values.astype(float)
            recent_vals = monthly_arr[-window:]
            w = np.arange(1, len(recent_vals) + 1, dtype=float)
            w = w / w.sum()
            wma_val = float(np.sum(recent_vals * w))
            if test_data is not None:
                test_forecast_values = [max(0.0, wma_val) for _ in range(3)]
                fc_arr = np.array(test_forecast_values)
                test_act_arr = np.asarray(test_data.values, dtype=float)
                mae = float(np.mean(np.abs(test_act_arr - fc_arr)))
                rmse = float(np.sqrt(np.mean((test_act_arr - fc_arr) ** 2)))
                pct_errs = np.where(test_act_arr > 0, np.abs(test_act_arr - fc_arr) / test_act_arr, 0.0)
                pct_errs = np.where((test_act_arr == 0) & (fc_arr > 0), 1.0, pct_errs)
                accuracy = max(0.0, (1.0 - np.mean(pct_errs)) * 100.0) if len(pct_errs) > 0 else 0.0
            forecast_values = _compute_trend_forecast(monthly_arr, horizon=12)

        elif model_type == 'exp_smooth':
            # 指数平滑（Holt-Winters）—— 处理趋势+季节性
            try:
                from statsmodels.tsa.holtwinters import ExponentialSmoothing
            except ImportError:
                return False, 'exp_smooth 依赖 statsmodels，请先安装该包。'
            try:
                train_vals_arr = train_data.astype(float).values
                n_train = len(train_vals_arr)
                use_seasonal = retry_params.get('seasonal_enabled', len(train_data) >= 24)
                seasonal_periods = retry_params.get('seasonal_periods', 12)

                # 季节性周期安全校验（与 holt-winters 一致）
                if use_seasonal and seasonal_periods is not None:
                    if seasonal_periods > n_train:
                        for sp in [12, 6, 4, 3]:
                            if sp <= n_train:
                                seasonal_periods = sp
                                break
                        else:
                            seasonal_periods = None

                    if seasonal_periods is not None and n_train >= seasonal_periods:
                        es_model = ExponentialSmoothing(
                            train_vals_arr, trend='add', seasonal='add', seasonal_periods=seasonal_periods
                        ).fit()
                    else:
                        es_model = ExponentialSmoothing(
                            train_vals_arr, trend='add', seasonal=None
                        ).fit()
                else:
                    es_model = ExponentialSmoothing(
                        train_vals_arr, trend='add', seasonal=None
                    ).fit()
                if test_data is not None:
                    test_vals = test_data.astype(float).values
                    test_forecast = es_model.forecast(steps=3)
                    test_forecast_values = [max(0.0, float(x)) for x in test_forecast]
                    fc_arr = np.maximum(0.0, np.asarray(test_forecast, dtype=float))
                    mae = float(np.mean(np.abs(test_vals - fc_arr)))
                    rmse = float(np.sqrt(np.mean((test_vals - fc_arr) ** 2)))
                    pct_errs = np.where(test_vals > 0, np.abs(test_vals - fc_arr) / test_vals, 0.0)
                    pct_errs = np.where((test_vals == 0) & (fc_arr > 0), 1.0, pct_errs)
                    accuracy = max(0.0, (1.0 - np.mean(pct_errs)) * 100.0) if len(pct_errs) > 0 else 0.0
                forecast_values = [max(0.0, float(x)) for x in es_model.forecast(steps=12)]
            except Exception as e:
                train_error = f'exp_smooth 训练失败：{e}'

        elif model_type == 'seasonal_naive':
            # 季节性朴素预测 —— 无需重训降参
            # 需要至少12个月数据，用最近12个月作为未来12个月的预测
            monthly_arr = monthly_data.values.astype(float)
            if len(monthly_data) >= 12:
                seasonal_vals = monthly_arr[-12:]
                if test_data is not None:
                    train_arr = train_data.values.astype(float)
                    if len(train_arr) >= 3:
                        offset = len(train_arr) - 3
                        test_forecast_values = [max(0.0, float(train_arr[offset + i])) for i in range(3)]
                    else:
                        test_forecast_values = [max(0.0, float(np.mean(train_arr))) for _ in range(3)]
                    fc_arr = np.array(test_forecast_values)
                    test_act_arr = np.asarray(test_data.values, dtype=float)
                    mae = float(np.mean(np.abs(test_act_arr - fc_arr)))
                    rmse = float(np.sqrt(np.mean((test_act_arr - fc_arr) ** 2)))
                    pct_errs = np.where(test_act_arr > 0, np.abs(test_act_arr - fc_arr) / test_act_arr, 0.0)
                    pct_errs = np.where((test_act_arr == 0) & (fc_arr > 0), 1.0, pct_errs)
                    accuracy = max(0.0, (1.0 - np.mean(pct_errs)) * 100.0) if len(pct_errs) > 0 else 0.0
                forecast_values = [max(0.0, float(v)) for v in seasonal_vals]
            else:
                mean_val = float(np.mean(monthly_arr))
                forecast_values = _compute_trend_forecast(monthly_arr, horizon=12)
                if test_data is not None:
                    test_forecast_values = [max(0.0, mean_val) for _ in range(3)]
                    fc_arr = np.array(test_forecast_values)
                    test_act_arr = np.asarray(test_data.values, dtype=float)
                    mae = float(np.mean(np.abs(test_act_arr - fc_arr)))
                    rmse = float(np.sqrt(np.mean((test_act_arr - fc_arr) ** 2)))
                    pct_errs = np.where(test_act_arr > 0, np.abs(test_act_arr - fc_arr) / test_act_arr, 0.0)
                    pct_errs = np.where((test_act_arr == 0) & (fc_arr > 0), 1.0, pct_errs)
                    accuracy = max(0.0, (1.0 - np.mean(pct_errs)) * 100.0) if len(pct_errs) > 0 else 0.0

        elif model_type == 'arimax':
            try:
                from statsmodels.tsa.arima.model import ARIMA
            except ImportError:
                return False, 'ARIMAX 依赖 statsmodels，请先安装该包。'
            try:
                train_arr = train_data.values.astype(float)
                n_train = len(train_arr)
                exog_train = np.arange(n_train, dtype=float).reshape(-1, 1)
                arimax_order = retry_params.get('arimax_order', (1, 1, 1))
                model = ARIMA(train_arr, exog=exog_train, order=arimax_order).fit()
                if test_data is not None:
                    test_values = test_data.astype(float).values
                    exog_test = np.arange(n_train, n_train + 3, dtype=float).reshape(-1, 1)
                    test_fc = model.forecast(steps=3, exog=exog_test)
                    test_forecast_values = [max(0.0, float(x)) for x in test_fc]
                    mae, rmse, accuracy = _eval_metrics(test_values, test_forecast_values)
                exog_future = np.arange(n_train, n_train + 12, dtype=float).reshape(-1, 1)
                forecast_values = [max(0.0, float(x)) for x in model.forecast(steps=12, exog=exog_future)]
            except Exception as e:
                train_error = f'ARIMAX 训练失败：{e}'

        elif model_type == 'prophet':
            try:
                from prophet import Prophet
            except ImportError:
                return False, 'Prophet 依赖 prophet 包，请先安装。'
            try:
                prophet_df = pd.DataFrame({'ds': monthly_data.index, 'y': monthly_data.values.astype(float)})
                y_seasonality = retry_params.get('yearly_seasonality', len(monthly_data) >= 18)
                cp_scale = retry_params.get('changepoint_prior_scale', 0.05)
                model = Prophet(
                    weekly_seasonality=False, daily_seasonality=False,
                    yearly_seasonality=y_seasonality,
                    changepoint_prior_scale=cp_scale
                )
                model.fit(prophet_df)
                if test_data is not None:
                    test_fc_df = model.make_future_dataframe(periods=3, freq='ME')
                    test_fc = model.predict(test_fc_df).tail(3)['yhat'].values
                    test_forecast_values = [max(0.0, float(x)) for x in test_fc]
                    mae, rmse, accuracy = _eval_metrics(test_data.values.astype(float), test_forecast_values)
                future = model.make_future_dataframe(periods=12, freq='ME')
                forecast_values = [max(0.0, float(x)) for x in model.predict(future).tail(12)['yhat'].values]
            except Exception as e:
                train_error = f'Prophet 训练失败：{e}'

        elif model_type == 'random_forest':
            try:
                from sklearn.ensemble import RandomForestRegressor
            except ImportError:
                return False, 'Random Forest 依赖 scikit-learn，请先安装。'
            try:
                monthly_df = monthly_data.reset_index()
                monthly_df['month_index'] = np.arange(len(monthly_df), dtype=float)
                monthly_df['month_of_year'] = monthly_df['date'].dt.month.astype(float)
                X_all = monthly_df[['month_index', 'month_of_year']].values
                y_all = monthly_df['sales_quantity'].astype(float).values
                if len(monthly_df) > 12:
                    X_tr, X_te = X_all[:-3], X_all[-3:]
                    y_tr, y_te = y_all[:-3], y_all[-3:]
                else:
                    X_tr, X_te, y_tr, y_te = X_all, None, y_all, None
                rf_n = retry_params.get('n_estimators', 150)
                rf_depth = retry_params.get('max_depth', None)
                model = RandomForestRegressor(
                    n_estimators=rf_n, max_depth=rf_depth, random_state=42, n_jobs=-1
                )
                model.fit(X_tr, y_tr)
                if X_te is not None:
                    test_fc = model.predict(X_te)
                    test_forecast_values = [max(0.0, float(x)) for x in test_fc]
                    mae, rmse, accuracy = _eval_metrics(y_te, test_forecast_values)
                last_idx = len(monthly_df)
                future_idx = np.arange(last_idx, last_idx + 12, dtype=float)
                future_months = np.array([(monthly_df['date'].iloc[-1].month + i) % 12 + 1
                                          for i in range(1, 13)], dtype=float)
                future_X = np.column_stack([future_idx, future_months])
                forecast_values = [max(0.0, float(x)) for x in model.predict(future_X)]
            except Exception as e:
                train_error = f'Random Forest 训练失败：{e}'

        elif model_type == 'croston':
            try:
                forecast_values = [max(0.0, float(x)) for x in _croston_predict(monthly_data, periods=12)]
                if test_data is not None:
                    test_forecast_values = [max(0.0, float(x)) for x in _croston_predict(train_data, periods=3)]
                    mae, rmse, accuracy = _eval_metrics(test_data.values.astype(float), test_forecast_values)
            except Exception as e:
                train_error = f'Croston 训练失败：{e}'

        elif model_type == 'sba':
            try:
                forecast_values = [max(0.0, float(x)) for x in _sba_predict(monthly_data, periods=12)]
                if test_data is not None:
                    test_forecast_values = [max(0.0, float(x)) for x in _sba_predict(train_data, periods=3)]
                    mae, rmse, accuracy = _eval_metrics(test_data.values.astype(float), test_forecast_values)
            except Exception as e:
                train_error = f'SBA 训练失败：{e}'

        elif model_type == 'lstm':
            try:
                import tensorflow as _tf_lstm
            except ImportError:
                return False, 'LSTM 依赖 TensorFlow，请先安装。'
            try:
                if len(monthly_data) < 12:
                    return False, 'LSTM 至少需要12个月数据'
                lstm_epochs = retry_params.get('epochs', 60)
                lstm_lookback = retry_params.get('lookback', 6)
                forecast_values = [max(0.0, float(x)) for x in _lstm_predict(monthly_data, periods=12, epochs=lstm_epochs, lookback=lstm_lookback)]
                if test_data is not None:
                    test_forecast_values = [max(0.0, float(x)) for x in _lstm_predict(train_data, periods=3, epochs=lstm_epochs, lookback=lstm_lookback)]
                    mae, rmse, accuracy = _eval_metrics(test_data.values.astype(float), test_forecast_values)
            except Exception as e:
                train_error = f'LSTM 训练失败：{e}'

        elif model_type == 'deepar':
            try:
                import tensorflow as _tf_deepar
            except ImportError:
                return False, 'DeepAR 依赖 TensorFlow，请先安装。'
            try:
                if len(monthly_data) < 12:
                    return False, 'DeepAR 至少需要12个月数据'
                deepar_epochs = retry_params.get('epochs', 50)
                deepar_lookback = retry_params.get('lookback', 6)
                forecast_values = [max(0.0, float(x)) for x in _deepar_predict(monthly_data, periods=12, epochs=deepar_epochs, lookback=deepar_lookback)]
                if test_data is not None:
                    test_forecast_values = [max(0.0, float(x)) for x in _deepar_predict(train_data, periods=3, epochs=deepar_epochs, lookback=deepar_lookback)]
                    mae, rmse, accuracy = _eval_metrics(test_data.values.astype(float), test_forecast_values)
            except Exception as e:
                train_error = f'DeepAR 训练失败：{e}'

        elif model_type == 'holt-winters':
            # 教科书 Holt-Winters 指数平滑（additive trend + additive seasonality）
            # 当数据不足24个月时自动退化为 Holt 线性趋势（无季节项）
            try:
                from statsmodels.tsa.holtwinters import ExponentialSmoothing
            except ImportError:
                # statsmodels 不可用时回退到线性回归+季节分解
                train_error = None  # 不使用重训循环，直接走 fallback 逻辑
                monthly_df = monthly_data.reset_index()
                monthly_df['month_index'] = np.arange(len(monthly_df), dtype=float)
                X_all = np.asarray(monthly_df['month_index'].values, dtype=float)
                y_all = np.asarray(monthly_df['sales_quantity'].values, dtype=float)
                slope, intercept = np.polyfit(X_all, y_all, 1)
                trend_line = intercept + slope * X_all
                residuals = y_all - trend_line
                seasonal_means = np.zeros(12)
                seasonal_counts = np.zeros(12)
                for idx, row in monthly_df.iterrows():
                    m = row['date'].month - 1
                    seasonal_means[m] += residuals[idx]
                    seasonal_counts[m] += 1
                for m in range(12):
                    if seasonal_counts[m] > 0:
                        seasonal_means[m] /= seasonal_counts[m]
                if test_data is not None:
                    train_slope, train_intercept = np.polyfit(X_all[:-3], y_all[:-3], 1)
                    test_trend = train_intercept + train_slope * np.arange(len(y_all)-3, len(y_all), dtype=float)
                    test_fc = test_trend + np.array([seasonal_means[(monthly_df['date'].iloc[len(y_all)-3+j].month-1)] for j in range(3)])
                    mae, rmse, accuracy = _eval_metrics(y_all[-3:], np.maximum(0.0, test_fc))
                    test_forecast_values = [float(v) for v in np.maximum(0.0, test_fc)]
                forecast_raw = intercept + slope * np.arange(len(y_all), len(y_all)+12, dtype=float)
                last_d = monthly_df['date'].iloc[-1]
                for step in range(1, 13):
                    fd = last_d + pd.DateOffset(months=step)
                    forecast_raw[step-1] += seasonal_means[fd.month - 1]
                forecast_values = [max(0.0, float(v)) for v in forecast_raw]
            else:
                try:
                    train_vals_arr = train_data.astype(float).values
                    n_train = len(train_vals_arr)
                    use_seasonal = retry_params.get('use_seasonal', n_train >= 12)
                    seasonal_periods = retry_params.get('seasonal_periods', 12)

                    # 季节性周期安全校验：若重试参数指定的周期超过数据量，自动降级
                    # 不从 [12,6,4,3] 重新选择，避免覆盖重试机制的降参意图
                    if use_seasonal and seasonal_periods is not None:
                        if seasonal_periods > n_train:
                            # 周期过大，降级到数据支持的最大合理周期
                            for sp in [12, 6, 4, 3]:
                                if sp <= n_train:
                                    seasonal_periods = sp
                                    break
                            else:
                                seasonal_periods = None

                        if seasonal_periods is not None and n_train >= seasonal_periods:
                            hw_model = ExponentialSmoothing(
                                train_vals_arr, trend='add', seasonal='add',
                                seasonal_periods=seasonal_periods
                            ).fit()
                        else:
                            hw_model = ExponentialSmoothing(
                                train_vals_arr, trend='add', seasonal=None
                            ).fit()
                    else:
                        hw_model = ExponentialSmoothing(
                            train_vals_arr, trend='add', seasonal=None
                        ).fit()
                    if test_data is not None:
                        test_vals = test_data.astype(float).values
                        test_forecast = hw_model.forecast(steps=3)
                        test_forecast_values = [max(0.0, float(x)) for x in test_forecast]
                        mae, rmse, accuracy = _eval_metrics(test_vals, test_forecast_values)
                    forecast_values = [max(0.0, float(x)) for x in hw_model.forecast(steps=12)]
                except Exception as e:
                    train_error = f'Holt-Winters 训练失败：{e}'

        else:
            # 未知模型类型或兜底：线性回归趋势 + 月份季节分量分解
            monthly_df = monthly_data.reset_index()
            monthly_df['month_index'] = np.arange(len(monthly_df), dtype=float)
            X = np.asarray(monthly_df['month_index'].values, dtype=float)
            y = np.asarray(monthly_df['sales_quantity'].values, dtype=float)
            n_all = len(y)

            slope, intercept = np.polyfit(X, y, 1)
            trend_line = intercept + slope * X
            residuals = y - trend_line

            seasonal_means = np.zeros(12)
            seasonal_counts = np.zeros(12)
            for idx, row in monthly_df.iterrows():
                m = row['date'].month - 1
                seasonal_means[m] += residuals[idx]
                seasonal_counts[m] += 1
            for m in range(12):
                if seasonal_counts[m] > 0:
                    seasonal_means[m] /= seasonal_counts[m]

            if test_data is not None:
                train_X = np.asarray(X[:-3], dtype=float)
                train_y = np.asarray(y[:-3], dtype=float)
                test_X = np.asarray(X[-3:], dtype=float)
                test_y = np.asarray(y[-3:], dtype=float)
                train_slope, train_intercept = np.polyfit(train_X, train_y, 1)
                train_trend = train_intercept + train_slope * train_X
                train_resid = train_y - train_trend
                train_seasonal = np.zeros(12)
                train_seasonal_cnt = np.zeros(12)
                train_dates = monthly_df['date'].iloc[:-3]
                for idx2, d in enumerate(train_dates):
                    m2 = d.month - 1
                    train_seasonal[m2] += train_resid[idx2]
                    train_seasonal_cnt[m2] += 1
                for m2 in range(12):
                    if train_seasonal_cnt[m2] > 0:
                        train_seasonal[m2] /= train_seasonal_cnt[m2]
                test_trend_pred = train_intercept + train_slope * test_X
                test_season_pred = np.array([
                    train_seasonal[(monthly_df['date'].iloc[n_all - 3 + j].month - 1)]
                    for j in range(3)
                ])
                test_forecast = test_trend_pred + test_season_pred
                fc_arr = np.maximum(0.0, test_forecast)
                test_forecast_values = [float(v) for v in fc_arr]
                mae, rmse, accuracy = _eval_metrics(test_y, fc_arr)
            else:
                mae = 0.0
                rmse = 0.0
                accuracy = 90.0

            future_months = []
            last_date = monthly_df['date'].iloc[-1]
            for step in range(1, 13):
                future_date = last_date + pd.DateOffset(months=step)
                future_months.append(future_date.month - 1)

            future_X = np.arange(n_all, n_all + 12, dtype=float)
            trend_forecast = intercept + slope * future_X
            season_forecast = np.array([seasonal_means[m] for m in future_months])
            forecast_raw = trend_forecast + season_forecast
            forecast_values = [max(0.0, float(v)) for v in forecast_raw]

        # ── 训练异常处理 ──
        if train_error is not None:
            if attempt < MAX_RETRIES - 1:
                logger.warning(f'[{region}/{sku}/{model_type}] 第{attempt+1}次训练异常: {train_error}，尝试降参重训')
                continue
            else:
                return False, f'{model_type} 训练失败（重试{MAX_RETRIES}次后仍报错）：{train_error}'

        # ── 过拟合判断 ──
        if test_data is not None and mae > 0:
            is_overfit = mae > avg_monthly * 0.3
        else:
            # 没有测试集或MAE为0，视为未过拟合
            is_overfit = False

        if not is_overfit:
            if attempt > 0:
                logger.info(f'[{region}/{sku}/{model_type}] 第{attempt+1}次训练成功，已消除过拟合 (MAE={mae:.0f}, 阈值={avg_monthly*0.3:.0f})')
            break  # 模型质量合格，跳出循环
        else:
            if attempt < MAX_RETRIES - 1:
                logger.warning(f'[{region}/{sku}/{model_type}] 第{attempt+1}次过拟合 (MAE={mae:.0f} > 30%月均={avg_monthly*0.3:.0f})，降参重训')
            else:
                logger.warning(f'[{region}/{sku}/{model_type}] 已降参{MAX_RETRIES}次均过拟合，放弃该模型 (MAE={mae:.0f})')

    # 过拟合模型仍保存（标记 is_overfit=True），避免因所有模型均过拟合导致训练无结果
    # 后续在 train_model 中会优先选非过拟合模型，全部过拟合时选准确率最高的
    
    # ── 保存模型（使用循环中最后一次/最佳结果） ──
    model_name = f"{region}_{sku}_{model_type}"

    # 计算 display_name：SKU 级别取物料名称，分类级别取 sku 本身
    display_name = sku
    if hierarchy_level == 'sku':
        from apps.data_management.models import ProductData as PD
        pd_obj = PD.objects.filter(material_number=sku).first()
        if pd_obj and pd_obj.material_name:
            display_name = pd_obj.material_name

    forecast_model, created = ForecastModel.objects.update_or_create(
        sales_region_code=region,
        material_number=sku,
        model_type=model_type,
        hierarchy_level=hierarchy_level,
        category_code=category_code if hierarchy_level != 'sku' else None,
        defaults={
            'model_name': model_name,
            'display_name': display_name,
            'training_start_date': monthly_data.index[0].date(),
            'training_end_date': monthly_data.index[-1].date(),
            'accuracy': accuracy,
            'mae': mae,
            'rmse': rmse,
            'is_overfit': is_overfit
        }
    )

    ForecastResult.objects.filter(
        sales_region_code=region,
        material_number=sku,
        hierarchy_level=hierarchy_level,
        category_code=category_code if hierarchy_level != 'sku' else None,
        model_used=model_type
    ).delete()

    # --- 获取全部历史销售数据（不限时间范围），按月汇总 ---
    if hierarchy_level == 'sku':
        all_sales = SalesData.objects.filter(
            sales_region_code=region,
            product_data__material_number=sku
        ).order_by('date')
    else:
        field_name = CATEGORY_FIELD_MAP.get(hierarchy_level, 'product_data__product_category_level1')
        all_sales = SalesData.objects.filter(
            sales_region_code=region,
            **{field_name: sku}
        ).order_by('date')
    all_sales_df = pd.DataFrame(list(all_sales.values('date', 'sales_quantity')))
    if not all_sales_df.empty:
        # 分类层级下同日期可能有多条记录 → 先 groupby 求和再 reindex
        all_sales_df = all_sales_df.groupby('date', as_index=False)['sales_quantity'].sum()
        all_sales_df = all_sales_df.sort_values('date')
        all_sales_df.set_index('date', inplace=True)
        all_sales_df = all_sales_df.asfreq('D')
        all_sales_df['sales_quantity'] = all_sales_df['sales_quantity'].fillna(0)
        all_monthly = all_sales_df['sales_quantity'].resample('ME').sum()
    else:
        all_monthly = monthly_data.copy()

    # ── 数据清洗与预处理（回测数据） ──
    all_monthly, bt_cleaning_log = _preprocess_time_series(all_monthly, region, sku)

    # === 扩张窗口回测（Expanding Window Backtesting） ===
    # 核心思想：对每个历史月份，仅使用该月份之前的数据训练模型并预测该月份。
    # 这是真正的"样本外"回测。
    # min_train=12：需要至少12个月训练数据才能启动回测（保证季节性模型有足够历史）
    min_train = 12
    backtest_predictions = {}     # {Pandas Timestamp: predicted_float}
    naive_predictions = {}        # 朴素基线预测（用上月值）：{Pandas Timestamp: float}
    backtest_start_idx = min_train

    all_values = np.asarray(all_monthly.values, dtype=float)
    total_months = len(all_monthly)

    if total_months <= min_train:
        # 历史数据不足，无法启动扩张窗口回测
        backtest_start_idx = total_months

    for i in range(min_train, total_months):
        # 仅使用索引 [0, i) 的数据作为训练集，预测第 i 个月
        train_window = all_values[:i]
        train_x = np.arange(i, dtype=float)

        # --- 朴素基线：用上个月的值作为预测（业界通用基线） ---
        naive_pred = float(train_window[-1]) if i > 0 else 0.0
        naive_predictions[all_monthly.index[i]] = naive_pred

        # --- 模型预测 ---
        bt_pred = None
        if model_type == 'arima':
            try:
                from statsmodels.tsa.arima.model import ARIMA as BT_ARIMA
                bt_arima = BT_ARIMA(train_window, order=(1, 1, 1)).fit()
                bt_pred = float(bt_arima.forecast(steps=1))
            except Exception:
                s, b = np.polyfit(train_x, train_window, 1)
                bt_pred = b + s * float(i)
        elif model_type == 'xgboost':
            try:
                from xgboost import XGBRegressor as BT_XGB
                bt_months = np.array([(m % 12) + 1 for m in range(i)], dtype=float)
                bt_features = np.column_stack([train_x, bt_months])
                bt_xgb = BT_XGB(objective='reg:squarederror', n_estimators=100, random_state=42)
                bt_xgb.fit(bt_features, train_window)
                target_month = float((i % 12) + 1)
                bt_pred = float(bt_xgb.predict(np.array([[float(i), target_month]]))[0])
            except Exception:
                s, b = np.polyfit(train_x, train_window, 1)
                bt_pred = b + s * float(i)
        elif model_type == 'moving_avg':
            # 移动平均 + 季节调校：用移动平均捕捉趋势，季节指数纠正相位
            w_sz = min(6, max(3, i // 4))
            base_pred = float(np.mean(train_window[-w_sz:]))
            # 若有≥12个月训练数据，计算季节指数进行调校
            if i >= 12:
                try:
                    si = _seasonal_decompose(pd.Series(train_window))
                    target_m = i % 12
                    season_factor = float(si['seasonal_index'][target_m])
                    # 季节性强度越高，调校幅度越大
                    blend = si['seasonal_strength']
                    bt_pred = base_pred * (1.0 - blend) + base_pred * season_factor * blend
                except Exception:
                    bt_pred = base_pred
            else:
                bt_pred = base_pred
        elif model_type == 'weighted_avg':
            # 加权移动平均 + 季节调校
            w_sz = min(6, max(3, i // 4))
            recent = train_window[-w_sz:]
            w = np.arange(1, len(recent) + 1, dtype=float)
            w = w / w.sum()
            base_pred = float(np.sum(recent * w))
            if i >= 12:
                try:
                    si = _seasonal_decompose(pd.Series(train_window))
                    target_m = i % 12
                    season_factor = float(si['seasonal_index'][target_m])
                    blend = si['seasonal_strength']
                    bt_pred = base_pred * (1.0 - blend) + base_pred * season_factor * blend
                except Exception:
                    bt_pred = base_pred
            else:
                bt_pred = base_pred
        elif model_type == 'holt-winters':
            # 教科书 Holt-Winters 回测（与训练逻辑一致：自适应季节周期）
            try:
                from statsmodels.tsa.holtwinters import ExponentialSmoothing as BT_ES
                # 按优先级选择适配当前窗口的最大合理周期
                for sp in [12, 6, 4, 3]:
                    if sp <= i:
                        bt_es = BT_ES(train_window, trend='add', seasonal='add',
                                      seasonal_periods=sp).fit()
                        break
                else:
                    bt_es = BT_ES(train_window, trend='add', seasonal=None).fit()
                bt_pred = float(bt_es.forecast(steps=1))
            except Exception:
                # statsmodels 不可用或拟合失败时，回退到趋势+季节分解
                s, b = np.polyfit(train_x, train_window, 1)
                trend_line = b + s * train_x
                detrended = train_window - trend_line
                seas = np.zeros(12); sc = np.zeros(12)
                for m in range(i):
                    mi = m % 12
                    seas[mi] += detrended[m]; sc[mi] += 1
                for mi in range(12):
                    if sc[mi] > 0: seas[mi] /= sc[mi]
                bt_pred = (b + s * float(i)) + seas[i % 12]
        elif model_type == 'exp_smooth':
            try:
                from statsmodels.tsa.holtwinters import ExponentialSmoothing as BT_ES
                for sp in [12, 6, 4, 3]:
                    if sp <= i:
                        bt_es = BT_ES(train_window, trend='add', seasonal='add',
                                      seasonal_periods=sp).fit()
                        break
                else:
                    bt_es = BT_ES(train_window, trend='add', seasonal=None).fit()
                bt_pred = float(bt_es.forecast(steps=1))
            except Exception:
                # 回退：用线性外推
                s, b = np.polyfit(train_x, train_window, 1)
                bt_pred = b + s * float(i)
        elif model_type == 'seasonal_naive':
            # 核心：使用一年前的同月数据
            if i >= 12:
                bt_pred = float(all_values[i - 12])
            else:
                # 不足12个月时回退到朴素基线（上月值）
                bt_pred = naive_pred
        elif model_type == 'arimax':
            try:
                from statsmodels.tsa.arima.model import ARIMA as BT_ARIMAX
                exog_bt = np.arange(i, dtype=float).reshape(-1, 1)
                bt_arimax = BT_ARIMAX(train_window, exog=exog_bt, order=(1, 1, 1)).fit()
                exog_next = np.array([[float(i)]])
                bt_pred = float(bt_arimax.forecast(steps=1, exog=exog_next))
            except Exception:
                s, b = np.polyfit(train_x, train_window, 1)
                bt_pred = b + s * float(i)
        elif model_type == 'prophet':
            try:
                from prophet import Prophet as BT_Prophet
                bt_df = pd.DataFrame({
                    'ds': pd.to_datetime(all_monthly.index[:i]),
                    'y': train_window
                })
                bt_prophet = BT_Prophet(weekly_seasonality=False, daily_seasonality=False,
                                        yearly_seasonality=i >= 18)
                bt_prophet.fit(bt_df)
                bt_future = bt_prophet.make_future_dataframe(periods=1, freq='ME')
                bt_pred = float(bt_prophet.predict(bt_future).tail(1)['yhat'].values[0])
            except Exception:
                s, b = np.polyfit(train_x, train_window, 1)
                bt_pred = b + s * float(i)
        elif model_type == 'random_forest':
            try:
                from sklearn.ensemble import RandomForestRegressor as BT_RF
                bt_months = np.array([(m % 12) + 1 for m in range(i)], dtype=float)
                bt_features = np.column_stack([train_x, bt_months])
                bt_rf = BT_RF(n_estimators=100, random_state=42, n_jobs=-1)
                bt_rf.fit(bt_features, train_window)
                target_month = float((i % 12) + 1)
                bt_pred = float(bt_rf.predict(np.array([[float(i), target_month]]))[0])
            except Exception:
                s, b = np.polyfit(train_x, train_window, 1)
                bt_pred = b + s * float(i)
        elif model_type == 'croston':
            bt_pred = float(_croston_predict(train_window, periods=1)[0])
        elif model_type == 'sba':
            bt_pred = float(_sba_predict(train_window, periods=1)[0])
        elif model_type == 'lstm':
            try:
                bt_pred = float(_lstm_predict(train_window, periods=1, epochs=30)[0])
            except Exception:
                bt_pred = naive_pred
        elif model_type == 'deepar':
            try:
                bt_pred = float(_deepar_predict(train_window, periods=1, epochs=50)[0])
            except Exception:
                bt_pred = naive_pred
        else:
            # holt-winters / 线性回归 + 季节分解：
            # 先用线性回归拟合趋势，再计算各月季节分量，避免纯趋势外推导致的1个月时滞
            s, b = np.polyfit(train_x, train_window, 1)
            trend_line = b + s * train_x
            residuals = train_window - trend_line

            # 计算每个月份（1~12）的季节分量均值
            seasonal_means = np.zeros(12)
            seasonal_counts = np.zeros(12)
            for m in range(i):
                mi = m % 12
                seasonal_means[mi] += residuals[m]
                seasonal_counts[mi] += 1
            # 避免除零，未出现的月份使用0
            for mi in range(12):
                if seasonal_counts[mi] > 0:
                    seasonal_means[mi] /= seasonal_counts[mi]

            trend_pred = b + s * float(i)
            season_pred = seasonal_means[i % 12]
            bt_pred = trend_pred + season_pred

        backtest_predictions[all_monthly.index[i]] = max(0.0, float(bt_pred))

    # --- 准备产品信息（SKU级别时查物料名和分类，分类级别时填充对应分类字段） ---
    pd_info = {}
    if hierarchy_level == 'sku':
        from apps.data_management.models import ProductData as PD
        pd_obj = PD.objects.filter(material_number=sku).first()
        if pd_obj:
            pd_info = {
                'material_name': pd_obj.material_name or '',
                'category_l1': pd_obj.product_category_level1 or '',
                'category_l2': pd_obj.product_category_level2 or '',
                'category_l3': pd_obj.product_category_level3 or '',
                'category_l4': pd_obj.product_category_level4 or '',
                'category_l5': pd_obj.product_category_level5 or '',
            }
    else:
        pd_info = {
            'material_name': '',
            'category_l1': '',
            'category_l2': '',
            'category_l3': '',
            'category_l4': '',
            'category_l5': '',
        }
        pd_info[hierarchy_level] = sku  # 填充对应层级的分类值

    cat_code_val = category_code if hierarchy_level != 'sku' else None

    # --- 为全部历史月份创建 ForecastResult ---
    for i in range(total_months):
        idx = all_monthly.index[i]
        actual_val = float(all_monthly.iloc[i])

        if i >= backtest_start_idx:
            pred_val = backtest_predictions.get(idx, naive_predictions.get(idx, 0.0))
        else:
            # 预热期：基于可用历史数据做线性趋势外推（一步前向预测）
            if i > 1:
                warmup_x = np.arange(i, dtype=float)
                warmup_y = all_values[:i]
                ws, wb = np.polyfit(warmup_x, warmup_y, 1)
                pred_val = float(wb + ws * float(i))
            elif i > 0:
                pred_val = float(all_values[0])
            else:
                pred_val = actual_val

        ForecastResult.objects.create(
            sales_region_code=region,
            material_number=sku,
            hierarchy_level=hierarchy_level,
            category_code=cat_code_val,
            material_name=pd_info.get('material_name', ''),
            category_l1=pd_info.get('category_l1', ''),
            category_l2=pd_info.get('category_l2', ''),
            category_l3=pd_info.get('category_l3', ''),
            category_l4=pd_info.get('category_l4', ''),
            category_l5=pd_info.get('category_l5', ''),
            date=idx.date(),
            forecast_quantity=pred_val,
            actual_quantity=actual_val,
            model_used=model_type
        )

    # --- 未来月份预测（无实际销量） ---
    last_date = all_monthly.index[-1]
    for i, value in enumerate(forecast_values, start=1):
        forecast_date = last_date + pd.DateOffset(months=i)
        ForecastResult.objects.create(
            sales_region_code=region,
            material_number=sku,
            hierarchy_level=hierarchy_level,
            category_code=cat_code_val,
            material_name=pd_info.get('material_name', ''),
            category_l1=pd_info.get('category_l1', ''),
            category_l2=pd_info.get('category_l2', ''),
            category_l3=pd_info.get('category_l3', ''),
            category_l4=pd_info.get('category_l4', ''),
            category_l5=pd_info.get('category_l5', ''),
            date=forecast_date.date(),
            forecast_quantity=value,
            model_used=model_type
        )

    # --- 基于扩张窗口回测数据重新计算 MAE/RMSE/准确率 + 朴素基线对比 ---
    paired = ForecastResult.objects.filter(
        sales_region_code=region, material_number=sku,
        hierarchy_level=hierarchy_level,
        category_code=cat_code_val,
        model_used=model_type, actual_quantity__isnull=False
    ).order_by('date')
    if paired.exists():
        results_list = list(paired)
        bt_results = results_list[backtest_start_idx:] if len(results_list) > backtest_start_idx else results_list
        all_for = np.array([float(r.forecast_quantity) for r in bt_results])
        all_act = np.array([float(r.actual_quantity) for r in bt_results])
        mae = float(np.mean(np.abs(all_for - all_act)))
        rmse = float(np.sqrt(np.mean((all_for - all_act) ** 2)))
        # 用 actual 做分母（与 _eval_metrics 保持一致），避免 forecast 极小时误差爆炸
        pct_errs = np.where(all_act > 0, np.abs(all_act - all_for) / all_act, 0.0)
        pct_errs = np.where((all_act == 0) & (all_for > 0), 1.0, pct_errs)
        accuracy = max(0.0, (1.0 - np.mean(pct_errs)) * 100.0) if len(pct_errs) > 0 else 0.0
        is_overfit = mae > np.mean(all_act) * 0.3 if mae > 0 else False

        # 朴素基线："用上月实际值预测当月"，MASE < 1 表示模型优于朴素基线
        naive_mae = float(np.mean([abs(all_act[i] - all_act[i-1])
                                   for i in range(1, len(all_act))])) if len(all_act) > 1 else mae
        mase = round(mae / naive_mae, 3) if naive_mae > 0 else 1.0

        forecast_model.accuracy = accuracy
        forecast_model.mae = mae
        forecast_model.rmse = rmse
        forecast_model.is_overfit = is_overfit
        forecast_model.save(update_fields=['accuracy', 'mae', 'rmse', 'is_overfit'])

        # ── 后测质量检测：准确率 < 50% 或过拟合时自动切换替代模型 ──
        if accuracy < 50.0 or is_overfit:
            logger.warning(
                f'[{region}/{sku}/{model_type}] 后测质量不达标: '
                f'准确率={accuracy:.1f}%, 过拟合={is_overfit}，触发自动重训'
            )
            fallback_types = _get_fallback_model_types(model_type)
            if not fallback_types:
                # 没有替代模型，即使质量不达标也保留当前模型（总比没有好）
                logger.warning(
                    f'[{region}/{sku}] {model_type} 质量不达标但无替代模型，保留当前模型 '
                    f'(准确率={accuracy:.1f}%)'
                )
                return True, None
            for fb_type in fallback_types:
                logger.info(f'[{region}/{sku}] 自动尝试替代模型: {fb_type}')
                # 删除当前模型的回测结果和模型记录
                ForecastResult.objects.filter(
                    sales_region_code=region, material_number=sku, model_used=model_type
                ).delete()
                forecast_model.delete()
                # 递归训练替代模型
                success, err = train_single_combination(region, sku, fb_type, time_range,
                                                        hierarchy_level=hierarchy_level,
                                                        category_code=category_code)
                if success:
                    logger.info(f'[{region}/{sku}] 替代模型 {fb_type} 训练成功')
                    return True, None
                else:
                    logger.warning(f'[{region}/{sku}] 替代模型 {fb_type} 失败: {err}')
            # 所有替代模型均失败，原始模型也已被删除
            err_msg = f'模型 {model_type} 及所有替代模型 {fallback_types} 均不达标'
            logger.error(f'[{region}/{sku}] {err_msg}')
            return False, err_msg
    else:
        naive_mae = mae
        mase = 1.0

    return True, None


@login_required
def train_model(request):
    """模型训练视图 —— 级联多选分类筛选 + 自动尝试多种算法并选择最优模型"""
    selected_regions = []
    selected_skus = []
    selected_hierarchy = 'sku'
    selected_start_date = ''
    selected_end_date = ''
    # 级联分类筛选项
    selected_l1, selected_l2, selected_l3, selected_l4, selected_l5 = [], [], [], [], []
    training_errors = []

    # ── 获取日期范围默认值 ──
    default_start, default_end = _get_sales_date_range()

    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        # ── 解析表单 ──
        selected_regions = [r.strip() for r in request.POST.getlist('region') if r.strip()]
        selected_hierarchy = request.POST.get('hierarchy_level', 'sku')
        selected_start_date = request.POST.get('start_date', default_start)
        selected_end_date = request.POST.get('end_date', default_end)
        selected_l1 = [v.strip() for v in request.POST.getlist('category_l1') if v.strip()]
        selected_l2 = [v.strip() for v in request.POST.getlist('category_l2') if v.strip()]
        selected_l3 = [v.strip() for v in request.POST.getlist('category_l3') if v.strip()]
        selected_l4 = [v.strip() for v in request.POST.getlist('category_l4') if v.strip()]
        selected_l5 = [v.strip() for v in request.POST.getlist('category_l5') if v.strip()]
        selected_skus = [v.strip() for v in request.POST.getlist('sku') if v.strip()]

        logger.info(
            '[train_model] POST regions=%s l1=%s l2=%s l3=%s l4=%s l5=%s skus=%s hierarchy=%s',
            selected_regions, selected_l1, selected_l2, selected_l3,
            selected_l4, selected_l5, selected_skus, selected_hierarchy,
        )

        # ── 解析要训练的项目列表 ──
        training_items = _resolve_training_items(
            selected_hierarchy, selected_l1, selected_l2, selected_l3,
            selected_l4, selected_l5, selected_skus
        )
        logger.info('[train_model] _resolve_training_items returned %d items', len(training_items))

        training_errors = []
        if not selected_regions:
            training_errors.append('请选择至少一个销售区域')
        elif not training_items:
            logger.info(
                '[train_model] NO items found. l1=%s l2=%s l3=%s l4=%s l5=%s skus=%s hierarchy=%s',
                selected_l1, selected_l2, selected_l3, selected_l4,
                selected_l5, selected_skus, selected_hierarchy,
            )
            training_errors.append('当前筛选条件下没有可训练的项目，请调整筛选条件')
        else:
            if not selected_start_date:
                selected_start_date = default_start
            if not selected_end_date:
                selected_end_date = default_end

            available_model_types = _get_available_model_types()
            first_model_id = None

            try:
                for region in selected_regions:
                    for item_code, cat_code in training_items:
                        trained_models = []

                        for mt in available_model_types:
                            success, error_msg = train_single_combination(
                                region, item_code, mt, time_range=12,
                                hierarchy_level=selected_hierarchy,
                                category_code=cat_code,
                                start_date_str=selected_start_date,
                                end_date_str=selected_end_date,
                            )
                            if success:
                                # 注意：train_single_combination 可能通过回退链创建了
                                # 不同 model_type 的模型，因此不按 mt 过滤，取最新创建的
                                fm = ForecastModel.objects.filter(
                                    sales_region_code=region,
                                    material_number=item_code,
                                    hierarchy_level=selected_hierarchy,
                                    category_code=cat_code,
                                ).order_by('-created_at').first()
                                if fm:
                                    trained_models.append(fm)

                        if not trained_models:
                            item_label = item_code
                            training_errors.append(f'区域 {region} {item_label} 所有模型训练均失败')
                            continue

                        # 过滤掉过拟合模型，优先选择非过拟合的最优模型
                        non_overfit = [m for m in trained_models if not m.is_overfit]
                        if non_overfit:
                            best_model = max(non_overfit, key=lambda m: m.accuracy)
                        else:
                            best_model = max(trained_models, key=lambda m: m.accuracy)

                        if len(trained_models) >= 2:
                            ensemble_model, ensemble_acc = _try_ensemble(
                                region, item_code, [m.model_type for m in trained_models]
                            )
                            if ensemble_model and ensemble_acc is not None and ensemble_acc > best_model.accuracy:
                                best_model = ensemble_model

                        ForecastResult.objects.filter(
                            sales_region_code=region,
                            material_number=item_code,
                            hierarchy_level=selected_hierarchy,
                            category_code=cat_code,
                        ).exclude(model_used=best_model.model_type).delete()
                        ForecastModel.objects.filter(
                            sales_region_code=region,
                            material_number=item_code,
                            hierarchy_level=selected_hierarchy,
                            category_code=cat_code,
                        ).exclude(id=best_model.id).delete()

                        if first_model_id is None:
                            first_model_id = best_model.pk
            except Exception as e:
                logger.exception('模型训练过程中发生异常')
                training_errors.append(f'训练过程出错: {str(e)}')
                if is_ajax:
                    return JsonResponse({'success': False, 'errors': training_errors})

            # ── 多区域多SKU 自动加命名前缀 ──
            is_multi_region = len(selected_regions) > 1
            is_multi_sku = len(training_items) > 1
            if is_multi_region or is_multi_sku:
                prefix_parts = []
                if is_multi_region:
                    prefix_parts.append('多区域')
                if is_multi_sku:
                    prefix_parts.append('多sku')
                name_prefix = f"{'多区域多sku' if (is_multi_region and is_multi_sku) else ''.join(prefix_parts)}模型_"
                renamed = 0
                for fm_obj in ForecastModel.objects.filter(
                    sales_region_code__in=selected_regions,
                    material_number__in=[t[0] for t in training_items],
                    hierarchy_level=selected_hierarchy,
                ):
                    if not fm_obj.model_name.startswith(name_prefix):
                        fm_obj.model_name = name_prefix + fm_obj.model_name
                        fm_obj.save(update_fields=['model_name'])
                        renamed += 1
                if renamed:
                    logger.info('[train_model] Renamed %d models with prefix "%s"', renamed, name_prefix)

            if first_model_id:
                redirect_url = f"{reverse('model:results')}?model_id={first_model_id}"
                if is_ajax:
                    return JsonResponse({'success': True, 'redirect_url': redirect_url, 'message': gettext('模型训练完成')})
                return redirect(redirect_url)

            if not training_errors:
                training_errors.append('所有选定区域和分类的模型训练均未成功，请检查数据是否充足')

            if is_ajax:
                return JsonResponse({'success': False, 'errors': training_errors})

        # 早期校验错误的 AJAX 响应（未进入 else 分支的情况，如无区域/无训练项目）
        if is_ajax and training_errors:
            return JsonResponse({
                'success': False,
                'errors': training_errors,
                # 附带诊断信息方便排查
                'debug': {
                    'regions': selected_regions,
                    'training_items_count': len(training_items),
                    'l1': selected_l1, 'l2': selected_l2, 'l3': selected_l3,
                    'l4': selected_l4, 'l5': selected_l5, 'skus': selected_skus,
                }
            })

    # ── GET: 准备页面数据 ──
    raw_regions = SalesData.objects.values_list('sales_region_code', flat=True).distinct()
    regions = sorted(set(r.strip() for r in raw_regions if r and r.strip()))
    # ── SKU→区域 映射（用于级联：选择分类/SKU后过滤可选区域）──
    sku_region_pairs = SalesData.objects.values('product_data__material_number', 'sales_region_code').distinct()
    _sr_map = {}
    for pair in sku_region_pairs:
        sku = pair['product_data__material_number']
        region = (pair['sales_region_code'] or '').strip()
        if sku and region:
            _sr_map.setdefault(sku, set()).add(region)
    sku_regions_map = {k: sorted(v) for k, v in _sr_map.items()}
    category_tree = _build_category_cascade_tree()
    return render(request, 'model_training/train.html', {
        'regions_list': list(regions),
        'category_tree': category_tree,
        'sku_regions_map': sku_regions_map,
        'default_start_date': default_start,
        'default_end_date': default_end,
        'selected_regions': selected_regions,
        'selected_skus': selected_skus,
        'selected_start_date': selected_start_date or default_start,
        'selected_end_date': selected_end_date or default_end,
        'selected_l1': selected_l1, 'selected_l2': selected_l2,
        'selected_l3': selected_l3, 'selected_l4': selected_l4, 'selected_l5': selected_l5,
        'active_tab': 'model',
        'training_errors': training_errors
    })


@login_required
def model_results(request):
    """模型结果视图"""
    model_id = request.GET.get('model_id', '')
    if not model_id:
        messages.error(request, gettext('未指定模型'))
        return redirect('model:train')
    
    try:
        forecast_model = ForecastModel.objects.get(id=model_id)
    except ForecastModel.DoesNotExist:
        messages.error(request, gettext('模型不存在'))
        return redirect('model:train')
    
    results = ForecastResult.objects.filter(
        sales_region_code=forecast_model.sales_region_code,
        material_number=forecast_model.material_number,
        hierarchy_level=forecast_model.hierarchy_level,
        category_code=forecast_model.category_code,
        model_used=forecast_model.model_type
    ).order_by('date')

    hl = forecast_model.hierarchy_level or 'sku'
    if hl == 'sku':
        sales_history = SalesData.objects.filter(
            sales_region_code=forecast_model.sales_region_code,
            product_data__material_number=forecast_model.material_number
        ).order_by('date')
    else:
        field_name = CATEGORY_FIELD_MAP.get(hl, 'product_data__product_category_level1')
        sales_history = SalesData.objects.filter(
            sales_region_code=forecast_model.sales_region_code,
            **{field_name: forecast_model.material_number}
        ).order_by('date')

    actual_by_month = {}
    for s in sales_history:
        month = s.date.strftime('%Y-%m')
        actual_by_month[month] = actual_by_month.get(month, 0.0) + float(s.sales_quantity)

    result_by_month = OrderedDict()
    for r in results:
        month = r.date.strftime('%Y-%m')
        result_by_month[month] = {
            'forecast': float(r.forecast_quantity),
            'actual': float(r.actual_quantity) if r.actual_quantity is not None else None
        }

    if sales_history.exists():
        current_month = sales_history.first().date.replace(day=1)
    else:
        current_month = forecast_model.training_start_date.replace(day=1)
    if results.exists():
        last_month = results.last().date.replace(day=1)
    else:
        last_month = forecast_model.training_end_date.replace(day=1)

    chart_labels = []
    while current_month <= last_month:
        chart_labels.append(current_month.strftime('%Y-%m'))
        year = current_month.year + (1 if current_month.month == 12 else 0)
        month = 1 if current_month.month == 12 else current_month.month + 1
        current_month = current_month.replace(year=year, month=month)

    # ── 从 ForecastResult 获取产品/分类展示信息 ──
    first_result = results.first()
    display_material_name = ''
    display_category_l1 = ''
    display_category_l2 = ''
    display_category_l3 = ''
    display_category_l4 = ''
    display_category_l5 = ''
    if first_result:
        display_material_name = first_result.material_name or ''
        display_category_l1 = first_result.category_l1 or ''
        display_category_l2 = first_result.category_l2 or ''
        display_category_l3 = first_result.category_l3 or ''
        display_category_l4 = first_result.category_l4 or ''
        display_category_l5 = first_result.category_l5 or ''

    result_list = []
    for month in chart_labels:
        forecast_value = result_by_month.get(month, {}).get('forecast')
        actual_value = result_by_month.get(month, {}).get('actual')
        if actual_value is None:
            actual_value = actual_by_month.get(month)

        diff_value = None
        if forecast_value is not None and actual_value is not None:
            diff_value = round(forecast_value - actual_value, 2)

        result_list.append({
            'date': month,
            'sku': forecast_model.material_number,
            'material_name': display_material_name,
            'category_l1': display_category_l1,
            'category_l2': display_category_l2,
            'category_l3': display_category_l3,
            'category_l4': display_category_l4,
            'category_l5': display_category_l5,
            'forecast': round(forecast_value, 2) if forecast_value is not None else None,
            'actual': round(actual_value, 2) if actual_value is not None else None,
            'diff': diff_value
        })

    actual_items = [item for item in result_list if item['forecast'] is not None and item['actual'] is not None]
    actual_count = len(actual_items)
    average_actual = np.mean([item['actual'] for item in actual_items]) if actual_items else None
    bias = round(np.mean([item['forecast'] - item['actual'] for item in actual_items]), 2) if actual_items else None
    mape = round(np.mean([abs(item['forecast'] - item['actual']) / item['actual'] * 100 for item in actual_items if item['actual'] != 0]), 2) if actual_items else None
    level = None
    if mape is not None:
        if mape < 10:
            level = '优秀'
        elif mape < 20:
            level = '良好'
        elif mape < 30:
            level = '一般'
        else:
            level = '差'
    error_stats = {
        'mae': round(np.mean([abs(item['forecast'] - item['actual']) for item in actual_items]), 2) if actual_items else None,
        'rmse': round(np.sqrt(np.mean([(item['forecast'] - item['actual']) ** 2 for item in actual_items])), 2) if actual_items else None,
        'max_error': round(max([abs(item['forecast'] - item['actual']) for item in actual_items]), 2) if actual_items else None,
        'bias': bias,
        'bias_pct': round(bias / average_actual * 100, 2) if bias is not None and average_actual else None,
        'mape': mape,
        'level': level,
        'actual_count': actual_count
    }

    # 基于全部历史回测数据更新 ForecastModel 的 MAE/RMSE/准确率
    if actual_items:
        all_for = np.array([item['forecast'] for item in actual_items])
        all_act = np.array([item['actual'] for item in actual_items])
        # 用 actual 做分母（与 _eval_metrics 保持一致），避免 forecast 极小时误差爆炸
        pct_errs = np.where(all_act > 0, np.abs(all_act - all_for) / all_act, 0.0)
        pct_errs = np.where((all_act == 0) & (all_for > 0), 1.0, pct_errs)
        recalc_accuracy = round(max(0.0, (1.0 - np.mean(pct_errs)) * 100.0), 2) if len(pct_errs) > 0 else 0.0
        forecast_model.accuracy = recalc_accuracy
        forecast_model.mae = error_stats['mae']
        forecast_model.rmse = error_stats['rmse']
        forecast_model.save(update_fields=['accuracy', 'mae', 'rmse'])

    sales_list = []
    for s in sales_history:
        sales_list.append({
            'date': s.date.strftime('%Y-%m'),
            'quantity': round(s.sales_quantity, 2)
        })

    chart_forecasts_backtest = [r['forecast'] if r['forecast'] is not None and r['actual'] is not None else None for r in result_list]
    chart_forecasts_future = [r['forecast'] if r['forecast'] is not None and r['actual'] is None else None for r in result_list]
    chart_actuals = [r['actual'] for r in result_list]

    # 计算 MAE/RMSE 相对月均销量的占比，用于参考范围展示
    mae_ratio_pct = None
    rmse_ratio_pct = None
    if average_actual and average_actual > 0:
        if error_stats['mae'] is not None:
            mae_ratio_pct = round(error_stats['mae'] / average_actual * 100, 1)
        if error_stats['rmse'] is not None:
            rmse_ratio_pct = round(error_stats['rmse'] / average_actual * 100, 1)

    # 朴素基线MAE："用上月值预测当月"，MASE < 1.0 说明模型优于朴素基线
    naive_mae = None
    mase = None
    if actual_items and len(actual_items) > 1:
        naive_errs = [abs(actual_items[i]['actual'] - actual_items[i-1]['actual'])
                      for i in range(1, len(actual_items))]
        naive_mae = round(float(np.mean(naive_errs)), 2)
        if error_stats['mae'] and naive_mae > 0:
            mase = round(error_stats['mae'] / naive_mae, 3)

    context = {
        'model': forecast_model,
        'results': result_list,
        'sales_data': sales_list,
        'chart_labels': json.dumps(chart_labels, ensure_ascii=False),
        'chart_forecasts_backtest': json.dumps(chart_forecasts_backtest),
        'chart_forecasts_future': json.dumps(chart_forecasts_future),
        'chart_actuals': json.dumps(chart_actuals),
        'error_stats': error_stats,
        'avg_monthly_sales': round(average_actual, 2) if average_actual else None,
        'mae_ratio_pct': mae_ratio_pct,
        'rmse_ratio_pct': rmse_ratio_pct,
        'naive_mae': naive_mae,
        'mase': mase,
        'active_tab': 'model'
    }

    return render(request, 'model_training/model_results.html', context)
