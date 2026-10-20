from django.utils.translation import gettext as _
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.views.decorators.cache import never_cache
from django.utils import timezone
import pandas as pd
import numpy as np
import json
from datetime import datetime
from io import BytesIO
from .models import ForecastScenario
from apps.model_training.models import ForecastModel, ForecastResult
from apps.model_training.views import (
    train_single_combination, CATEGORY_FIELD_MAP, HIERARCHY_LABEL_MAP,
    _build_category_cascade_tree, _resolve_training_items, _get_sales_date_range,
    _get_available_model_types
)
from django.contrib.auth.decorators import login_required
from apps.data_management.models import ProductData, SalesData, PromotionData


def _build_hierarchy_item_map(hierarchy_level='sku'):
    """构建 区域 → 可选项目(SKU或分类) 映射"""
    if hierarchy_level == 'sku':
        pairs = ForecastModel.objects.filter(hierarchy_level='sku').order_by(
            'sales_region_code', 'material_number'
        ).values('sales_region_code', 'material_number').distinct()
    else:
        pairs = ForecastModel.objects.filter(hierarchy_level=hierarchy_level).order_by(
            'sales_region_code', 'material_number'
        ).values('sales_region_code', 'material_number').distinct()
    region_items = {}
    for pair in pairs:
        region_items.setdefault(pair['sales_region_code'], []).append(pair['material_number'])
    return {region: sorted(list(set(items))) for region, items in region_items.items()}


def _build_region_sku_map():
    """向后兼容：SKU级别映射"""
    return _build_hierarchy_item_map('sku')


def _collect_forecast_data(region, sku, forecast_period, hierarchy_level='sku', category_code=None, model_id=None):
    cat_code = category_code if hierarchy_level != 'sku' else None

    # ── 回退链：从当前层级向上逐级查找模型 ──
    # 当用户选中一个 SKU 但没有对应 SKU 级模型时，尝试用 category_l5→l4→l3→l2→l1
    def _build_sku_fallback_levels(sku_val):
        """为 SKU 构建回退层级列表 [(hierarchy_level, material_number, category_code), ...]"""
        fallback = []
        try:
            pd_obj = ProductData.objects.filter(material_number=sku_val).first()
            if pd_obj:
                # SKU → L5 → L4 → L3 → L2 → L1
                level_cat_map = [
                    ('category_l5', getattr(pd_obj, 'product_category_level5', None)),
                    ('category_l4', getattr(pd_obj, 'product_category_level4', None)),
                    ('category_l3', getattr(pd_obj, 'product_category_level3', None)),
                    ('category_l2', getattr(pd_obj, 'product_category_level2', None)),
                    ('category_l1', getattr(pd_obj, 'product_category_level1', None)),
                ]
                for lvl, val in level_cat_map:
                    if val and val.strip():
                        fallback.append((lvl, val.strip(), val.strip()))
        except Exception:
            pass
        return fallback

    if model_id:
        # ── 用户手动指定了模型，直接使用 ──
        try:
            model = ForecastModel.objects.get(id=model_id)
            # 使用模型自身的 hierarchy_level / material_number 查结果
            search_level = model.hierarchy_level
            search_sku = model.material_number
            search_cat = model.category_code or None
        except ForecastModel.DoesNotExist:
            raise ValueError(f'指定的模型 (ID={model_id}) 不存在')
    else:
        # ── 自动匹配最佳模型（含回退）──
        model = None
        search_level = hierarchy_level
        search_sku = sku
        search_cat = cat_code

        # 先精确查询
        model = ForecastModel.objects.filter(
            sales_region_code=region,
            material_number=search_sku,
            hierarchy_level=search_level,
            category_code=search_cat,
        ).order_by('-created_at').first()

        # 若精确匹配失败，逐级回退
        if not model:
            if hierarchy_level == 'sku':
                fallback_levels = _build_sku_fallback_levels(sku)
                for fl_level, fl_sku, fl_cat in fallback_levels:
                    model = ForecastModel.objects.filter(
                        sales_region_code=region,
                        material_number=fl_sku,
                        hierarchy_level=fl_level,
                        category_code=fl_cat,
                    ).order_by('-created_at').first()
                    if model:
                        search_level = fl_level
                        search_sku = fl_sku
                        search_cat = fl_cat
                        break
                if not model:
                    # ── 自动触发模型训练 ──
                    import logging
                    _logger = logging.getLogger('demand_prediction')
                    trained = False
                    # 优先尝试 SKU 级别，再回退到 L5→L4→L3→L2→L1
                    levels_to_train = [('sku', sku, cat_code)] + _build_sku_fallback_levels(sku)
                    # 只用快速模型（跳过 ARIMA/RandomForest，它们在同步请求中太慢）
                    fast_models = ['holt-winters', 'seasonal_naive', 'moving_avg',
                                   'weighted_avg', 'croston', 'sba']
                    for try_level, try_material, try_cat in levels_to_train:
                        level_trained = False
                        for mtype in fast_models:
                            try:
                                success, msg = train_single_combination(
                                    region, try_material,
                                    model_type=mtype, time_range=12,
                                    hierarchy_level=try_level,
                                    category_code=try_cat,
                                )
                                if success:
                                    level_trained = True
                            except Exception as e:
                                _logger.warning(f'Auto-train {mtype} for {try_level}/{try_material} failed: {e}')
                        if level_trained:
                            trained = True
                            model = ForecastModel.objects.filter(
                                sales_region_code=region,
                                material_number=try_material,
                                hierarchy_level=try_level,
                                category_code=try_cat,
                            ).order_by('-created_at').first()
                            if model:
                                search_level = try_level
                                search_sku = try_material
                                search_cat = try_cat
                            break
                    if not model:
                        raise ValueError(
                            f'未找到区域 {region} SKU {sku} 及其上级分类的训练模型，'
                            f'自动训练也未成功，请手动训练模型'
                        )
            else:
                # ── 自动触发分类级别模型训练 ──
                import logging
                _logger = logging.getLogger('demand_prediction')
                fast_models = ['holt-winters', 'seasonal_naive', 'moving_avg',
                               'weighted_avg', 'croston', 'sba']
                for mtype in fast_models:
                    try:
                        train_single_combination(
                            region, sku, model_type=mtype, time_range=12,
                            hierarchy_level=hierarchy_level, category_code=cat_code,
                        )
                    except Exception:
                        pass
                # 重试查找
                model = ForecastModel.objects.filter(
                    sales_region_code=region,
                    material_number=sku,
                    hierarchy_level=hierarchy_level,
                    category_code=cat_code,
                ).order_by('-created_at').first()
                if not model:
                    raise ValueError(
                        f'未找到区域 {region} 分类 {sku} 的训练模型，'
                        f'自动训练也未成功，请手动训练'
                    )

    all_results = ForecastResult.objects.filter(
        sales_region_code=region,
        material_number=search_sku,
        hierarchy_level=search_level,
        category_code=search_cat,
        model_used=model.model_type
    ).order_by('date')
    if not all_results.exists():
        if search_level == 'sku':
            raise ValueError(f'未找到区域 {region} SKU {search_sku} 的预测结果，请先预测后再试')
        else:
            raise ValueError(f'未找到区域 {region} 分类 {search_sku} 的预测结果，请先预测后再试')

    # ── 用搜索到的层级（search_level）进行后续查询 ──
    # 覆盖值以便后续 sales/backtest 查询使用正确的层级
    if search_level != hierarchy_level:
        hierarchy_level = search_level
        sku = search_sku
        cat_code = search_cat

    if hierarchy_level == 'sku':
        sales_records = SalesData.objects.filter(
            sales_region_code=region,
            product_data__material_number=sku
        ).order_by('date')
    else:
        field_name = CATEGORY_FIELD_MAP.get(hierarchy_level, 'product_data__product_category_level1')
        sales_records = SalesData.objects.filter(
            sales_region_code=region,
            **{field_name: sku}
        ).order_by('date')

    actual_by_month = {}
    for s in sales_records:
        month = s.date.strftime('%Y-%m')
        actual_by_month[month] = actual_by_month.get(month, 0.0) + float(s.sales_quantity)

    if sales_records.exists():
        earliest_label = sales_records.first().date.replace(day=1)
    else:
        earliest_label = all_results.first().date.replace(day=1)
    last_label = all_results.last().date.replace(day=1)

    chart_labels = []
    current_month = earliest_label
    while current_month <= last_label:
        chart_labels.append(current_month.strftime('%Y-%m'))
        year = current_month.year + (1 if current_month.month == 12 else 0)
        month = 1 if current_month.month == 12 else current_month.month + 1
        current_month = current_month.replace(year=year, month=month)

    result_map = {r.date.strftime('%Y-%m'): r for r in all_results}

    # --- 缺回测月份时，用线性回归补算（使图表始终展示完整回测线） ---
    sales_months = sorted(actual_by_month.keys())
    fallback_preds = {}
    if sales_months:
        sx = np.arange(len(sales_months), dtype=float)
        sy = np.array([actual_by_month[m] for m in sales_months], dtype=float)
        bt_slope, bt_intercept = np.polyfit(sx, sy, 1)
        for i, m_label in enumerate(sales_months):
            if m_label in chart_labels and m_label not in result_map:
                fallback_preds[m_label] = max(0.0, float(bt_intercept + bt_slope * i))

    chart_originals = []
    chart_adjusted = []
    chart_backtest = []
    chart_future = []
    chart_actuals = []
    for label in chart_labels:
        result = result_map.get(label)
        if result:
            original = float(result.forecast_quantity)
        elif label in fallback_preds:
            original = fallback_preds[label]
        else:
            original = None
        adjusted = float(result.adjusted_forecast_quantity) if result and result.adjusted_forecast_quantity is not None else original
        actual = actual_by_month.get(label)
        has_actual = actual is not None
        if result and has_actual:
            chart_backtest.append(original)
            chart_future.append(None)
        elif (result or label in fallback_preds) and has_actual:
            chart_backtest.append(original)
            chart_future.append(None)
        elif result:
            chart_backtest.append(None)
            chart_future.append(original)
        else:
            chart_backtest.append(None)
            chart_future.append(None)
        chart_originals.append(original)
        chart_adjusted.append(adjusted)
        chart_actuals.append(actual if has_actual else None)

    adjusted_results = []
    for result in all_results:
        month = result.date.strftime('%Y-%m')
        actual_value = result.actual_quantity if result.actual_quantity is not None else actual_by_month.get(month)
        original_forecast = round(float(result.forecast_quantity), 2)
        adjusted_forecast = round(float(result.adjusted_forecast_quantity), 2) if result.adjusted_forecast_quantity is not None else original_forecast
        diff_value = round(adjusted_forecast - float(actual_value), 2) if actual_value is not None else None
        adjusted_results.append({
            'id': result.id,
            'date': month,
            'actual': round(actual_value, 2) if actual_value is not None else None,
            'original_forecast': original_forecast,
            'adjusted_forecast': adjusted_forecast,
            'diff': diff_value,
            'material_name': result.material_name or '',
            'category_l1': result.category_l1 or '',
            'category_l2': result.category_l2 or '',
            'category_l3': result.category_l3 or '',
            'category_l4': result.category_l4 or '',
            'category_l5': result.category_l5 or '',
        })

    sales_list = [{
        'date': s.date.strftime('%Y-%m'),
        'quantity': round(s.sales_quantity, 2)
    } for s in sales_records]

    return {
        'model': model,
        'chart_labels': chart_labels,
        'chart_originals': chart_originals,
        'chart_adjusted': chart_adjusted,
        'chart_backtest': chart_backtest,
        'chart_future': chart_future,
        'chart_actuals': chart_actuals,
        'adjusted_results': adjusted_results,
        'sales_list': sales_list
    }

@login_required
@never_cache
def demand_forecast(request):
    """需求预测视图 —— 级联多选分类筛选 + 模型选择 + 自动训练"""
    default_start, default_end = _get_sales_date_range()

    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        try:
            selected_regions = [r.strip() for r in request.POST.getlist('region') if r.strip()]
            hierarchy_level = request.POST.get('hierarchy_level', 'sku')
            selected_start_date = request.POST.get('start_date', default_start)
            selected_end_date = request.POST.get('end_date', default_end)
            selected_l1 = [v.strip() for v in request.POST.getlist('category_l1') if v.strip()]
            selected_l2 = [v.strip() for v in request.POST.getlist('category_l2') if v.strip()]
            selected_l3 = [v.strip() for v in request.POST.getlist('category_l3') if v.strip()]
            selected_l4 = [v.strip() for v in request.POST.getlist('category_l4') if v.strip()]
            selected_l5 = [v.strip() for v in request.POST.getlist('category_l5') if v.strip()]
            selected_skus = [v.strip() for v in request.POST.getlist('sku') if v.strip()]
            model_mode = request.POST.get('model_mode', 'auto')

            try:
                forecast_period = int(request.POST.get('forecast_period', 12))
            except ValueError:
                forecast_period = 12
            if forecast_period < 1:
                forecast_period = 12

            # 解析要预测的项目列表
            training_items = _resolve_training_items(
                hierarchy_level, selected_l1, selected_l2, selected_l3,
                selected_l4, selected_l5, selected_skus
            )

            if not selected_regions:
                if is_ajax:
                    return JsonResponse({'success': False, 'errors': [_('请选择至少一个销售区域')]})
                messages.error(request, _('请选择至少一个销售区域'))
                return redirect('forecast:forecast')
            if not training_items:
                if is_ajax:
                    return JsonResponse({'success': False, 'errors': [_('当前筛选条件下没有可预测的项目，请调整筛选条件')],
                                         'debug': {'regions': selected_regions, 'l1': selected_l1, 'l2': selected_l2,
                                                   'l3': selected_l3, 'l4': selected_l4, 'l5': selected_l5,
                                                   'skus': selected_skus}})
                messages.error(request, _('当前筛选条件下没有可预测的项目，请调整筛选条件'))
                return redirect('forecast:forecast')

            # ── 模型匹配逻辑 ──
            # 如果用户手动选择了模型，则使用该模型；否则自动匹配
            selected_model_id = request.POST.get('selected_model_id', '').strip()
            use_selected_model = model_mode == 'select' and selected_model_id
            model_matched = None

            if use_selected_model:
                try:
                    model_matched = ForecastModel.objects.get(id=int(selected_model_id))
                except (ValueError, ForecastModel.DoesNotExist):
                    if is_ajax:
                        return JsonResponse({'success': False, 'errors': [_('所选模型不存在')]})
                    messages.error(request, _('所选模型不存在'))
                    return redirect('forecast:forecast')

            combos = []
            errors = []
            for region in selected_regions:
                for item_code, cat_code in training_items:
                    # ① 检查数据是否存在
                    if hierarchy_level == 'sku':
                        has_data = SalesData.objects.filter(
                            sales_region_code=region,
                            product_data__material_number=item_code
                        ).exists()
                    else:
                        field_name = CATEGORY_FIELD_MAP.get(hierarchy_level, 'product_data__product_category_level1')
                        has_data = SalesData.objects.filter(
                            sales_region_code=region,
                            **{field_name: item_code}
                        ).exists()
                    if not has_data:
                        continue

                    cat_code_q = cat_code if hierarchy_level != 'sku' else None

                    # ② 模型匹配 / 自动训练
                    if use_selected_model:
                        # 用户手动选择了模型，直接用它（验证区域/SKU匹配）
                        match_checks = []
                        if model_matched.sales_region_code != region:
                            match_checks.append(f'区域不匹配(模型:{model_matched.sales_region_code}≠当前:{region})')
                        if model_matched.material_number != item_code:
                            match_checks.append(f'物料不匹配(模型:{model_matched.material_number}≠当前:{item_code})')
                        if model_matched.hierarchy_level != hierarchy_level:
                            match_checks.append(f'层级不匹配(模型:{model_matched.hierarchy_level}≠当前:{hierarchy_level})')
                        if model_matched.category_code != cat_code_q:
                            match_checks.append(f'分类码不匹配(模型:{model_matched.category_code}≠当前:{cat_code_q})')
                        if match_checks:
                            detail = "; ".join(match_checks)
                            errors.append(f'模型[{model_matched.model_type}]与[{region}/{item_code}]不匹配: {detail}')
                            continue
                    else:
                        # 自动匹配：查找最近训练的匹配模型
                        model_exists = ForecastModel.objects.filter(
                            sales_region_code=region,
                            material_number=item_code,
                            hierarchy_level=hierarchy_level,
                            category_code=cat_code_q,
                        ).order_by('-created_at').first()
                        if not model_exists:
                            # 无匹配模型 → 自动触发训练
                            train_ok, train_err = train_single_combination(
                                region, item_code, hierarchy_level=hierarchy_level,
                                category_code=cat_code_q,
                                start_date_str=selected_start_date, end_date_str=selected_end_date,
                            )
                            if not train_ok:
                                errors.append(f'自动训练失败 [{region}/{item_code}]: {train_err}')
                                continue

                    # ③ 执行预测
                    try:
                        fd = _collect_forecast_data(region, item_code, forecast_period,
                                                    hierarchy_level=hierarchy_level,
                                                    category_code=cat_code_q)
                        combos.append((region, item_code, fd))
                    except Exception as e:
                        errors.append(str(e))

            if not combos:
                err_msg = '所有选中组合均预测失败' + ('：' + '; '.join(errors) if errors else '')
                if is_ajax:
                    return JsonResponse({'success': False, 'errors': [err_msg]})
                raise ValueError(err_msg)

            scenario_name = f"多组合预测_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            scenario = ForecastScenario.objects.create(
                name=scenario_name,
                description=f"预测周期: {forecast_period}个月，共{len(combos)}个组合",
                created_by=request.user.username if request.user.is_authenticated else 'anonymous',
                region=combos[0][0],
                sku=combos[0][1],
                forecast_period=forecast_period,
                hierarchy_level=hierarchy_level,
            )

            all_forecasts = []
            all_chart_data = []
            total_accuracy = 0.0
            for region, item_code, fd in combos:
                for item in fd['adjusted_results']:
                    all_forecasts.append({
                        'region': region,
                        'sku': item_code,
                        **item
                    })
                all_chart_data.append({
                    'region': region,
                    'sku': item_code,
                    'chart_labels': fd['chart_labels'],
                    'chart_backtest': fd['chart_backtest'],
                    'chart_future': fd['chart_future'],
                    'chart_actuals': fd['chart_actuals'],
                })
                total_accuracy += fd['model'].accuracy

            context = {
                'combos': [{'region': r, 'sku': s} for r, s, _ in combos],
                'forecasts': all_forecasts,
                'total_combos': len(combos),
                'scenario_name': scenario.name,
                'hierarchy_level': hierarchy_level,
                'model_accuracy': round(total_accuracy / len(combos), 2),
                'all_chart_data_json': json.dumps(all_chart_data, ensure_ascii=False),
                'active_tab': 'forecast',
                'warning_errors': errors if errors else None,
            }
            if is_ajax:
                # 将结果数据存入 session 供 results 页面读取
                request.session['_forecast_context'] = context
                request.session['_forecast_scenario_id'] = scenario.id
                from django.urls import reverse
                redirect_url = reverse('forecast:results_page')
                return JsonResponse({'success': True, 'redirect_url': redirect_url,
                                     'message': _('预测完成')})
            return render(request, 'demand_prediction/results.html', context)
        except Exception as e:
            if is_ajax:
                return JsonResponse({'success': False, 'errors': [str(e)]})
            messages.error(request, _(f'预测失败: {str(e)}'))
            return redirect('forecast:forecast')

    # GET: 准备页面数据
    # ── 区域去重（strip 空格后再去重） ──
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

    # ── 最近训练的模型（供用户选择） ──
    recent_models_qs = ForecastModel.objects.order_by('-created_at')[:30]
    recent_models = []
    for m in recent_models_qs:
        # 构建显示标签
        region_label = m.sales_region_code
        sku_label = m.material_number
        if m.hierarchy_level == 'sku':
            pd_obj = ProductData.objects.filter(material_number=m.material_number).first()
            if pd_obj and pd_obj.material_name:
                sku_label = f'{m.material_number} | {pd_obj.material_name}'
        else:
            label_key = HIERARCHY_LABEL_MAP.get(m.hierarchy_level, m.hierarchy_level)
            sku_label = f'[{label_key}] {m.material_number}'
        display_name = m.model_name
        if m.display_name:
            display_name = m.display_name
        recent_models.append({
            'id': m.id,
            'model_name': m.model_name,
            'display_name': display_name,
            'sales_region_code': m.sales_region_code,
            'region_label': region_label,
            'material_number': m.material_number,
            'sku_label': sku_label,
            'hierarchy_level': m.hierarchy_level,
            'category_code': m.category_code or '',
            'model_type': m.model_type,
            'accuracy': m.accuracy,
            'created_at': m.created_at.astimezone(timezone.get_current_timezone()).strftime('%Y-%m-%d %H:%M') if m.created_at else '',
        })

    # 序列化供前端分页使用
    recent_models_json = json.dumps(recent_models, ensure_ascii=False, default=str)

    return render(request, 'demand_prediction/forecast.html', {
        'regions_list': regions,
        'category_tree': category_tree,
        'sku_regions_map': sku_regions_map,
        'default_start_date': default_start,
        'default_end_date': default_end,
        'recent_models': recent_models,
        'recent_models_json': recent_models_json,
        'active_tab': 'forecast'
    })

@login_required
def export_forecast(request):
    """导出预测结果"""
    scenario_id = request.GET.get('scenario_id', '')
    if not scenario_id:
        messages.error(request, _('未指定预测场景'))
        return redirect('forecast:forecast')
    
    try:
        scenario = ForecastScenario.objects.get(id=scenario_id)
    except ForecastScenario.DoesNotExist:
        messages.error(request, _('预测场景不存在'))
        return redirect('forecast:forecast')
    
    results = ForecastResult.objects.filter(
        sales_region_code=scenario.region,
        material_number=scenario.sku
    ).order_by('date')[:scenario.forecast_period]
    
    data = []
    material_name = ProductData.objects.filter(material_number=scenario.sku).values_list('material_name', flat=True).first() or 'N/A'
    for result in results:
        adjusted_forecast = result.adjusted_forecast_quantity if result.adjusted_forecast_quantity is not None else result.forecast_quantity
        data.append({
            '预测日期': result.date.strftime('%Y-%m'),
            '原始预测销量': round(result.forecast_quantity, 2),
            '调整后预测销量': round(float(adjusted_forecast), 2),
            '销售区域': scenario.region,
            '物料号': scenario.sku,
            '物料名称': material_name
        })
    
    df = pd.DataFrame(data)
    
    # 创建Excel文件
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='预测结果')
        
        # 获取工作表并设置格式
        worksheet = writer.sheets['预测结果']
        workbook = writer.book
        
        # 标题格式
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4472C4',
            'font_color': 'white',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        })
        
        # 数据格式
        data_format = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        })
        
        # 设置列宽
        worksheet.set_column('A:A', 12)
        worksheet.set_column('B:C', 16)
        worksheet.set_column('D:D', 12)
        worksheet.set_column('E:E', 22)
        worksheet.set_column('F:F', 24)
        
        # 写入标题
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
        
        # 写入数据
        for row_num in range(len(df)):
            for col_num in range(len(df.columns)):
                worksheet.write(row_num + 1, col_num, df.iloc[row_num, col_num], data_format)
    
    output.seek(0)
    
    # 返回Excel文件
    response = HttpResponse(output.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename=forecast_{scenario.region}_{scenario.sku}_{datetime.now().strftime("%Y%m%d")}.xlsx'
    
    return response

@login_required
def update_adjusted_forecast(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': _('仅支持 POST 请求')})

    try:
        payload = json.loads(request.body.decode('utf-8'))
        result_id = int(payload.get('result_id'))
        adjusted_quantity = float(payload.get('adjusted_forecast'))
        result = ForecastResult.objects.get(id=result_id)
        result.adjusted_forecast_quantity = adjusted_quantity
        result.save(update_fields=['adjusted_forecast_quantity'])

        actual_value = result.actual_quantity
        if actual_value is None:
            from apps.data_management.models import SalesData
            year = result.date.year
            month = result.date.month
            month_start = result.date.replace(day=1)
            if month == 12:
                month_end = result.date.replace(year=year + 1, month=1, day=1)
            else:
                month_end = result.date.replace(month=month + 1, day=1)
            sales_qs = SalesData.objects.filter(
                sales_region_code=result.sales_region_code,
                product_data__material_number=result.material_number,
                date__gte=month_start,
                date__lt=month_end
            )
            total_sales = sum(float(s.sales_quantity) for s in sales_qs)
            actual_value = total_sales if sales_qs.exists() else None

        diff_value = round(adjusted_quantity - float(actual_value), 2) if actual_value is not None else None
        return JsonResponse({'success': True, 'adjusted_forecast': adjusted_quantity, 'diff': diff_value})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})

@login_required
def results_page(request):
    """从 session 读取预测结果并展示"""
    context = request.session.pop('_forecast_context', None)
    scenario_id = request.session.pop('_forecast_scenario_id', None)
    if not context:
        messages.error(request, _('未找到预测结果，请重新执行预测'))
        return redirect('forecast:forecast')
    context['active_tab'] = 'forecast'
    context['scenario_id'] = scenario_id
    return render(request, 'demand_prediction/results.html', context)


@login_required
@never_cache
def refresh_models(request):
    """AJAX: 刷新模型列表（训练完成后前端手动刷新）"""
    from apps.data_management.models import ProductData as PD
    recent_models_qs = ForecastModel.objects.order_by('-created_at')[:50]
    recent_models = []
    for m in recent_models_qs:
        region_label = m.sales_region_code
        sku_label = m.material_number
        if m.hierarchy_level == 'sku':
            pd_obj = PD.objects.filter(material_number=m.material_number).first()
            if pd_obj and pd_obj.material_name:
                sku_label = f'{m.material_number} | {pd_obj.material_name}'
        else:
            label_key = HIERARCHY_LABEL_MAP.get(m.hierarchy_level, m.hierarchy_level)
            sku_label = f'[{label_key}] {m.material_number}'
        display_name = m.display_name or m.model_name
        recent_models.append({
            'id': m.id,
            'model_name': m.model_name,
            'display_name': display_name,
            'sales_region_code': m.sales_region_code,
            'region_label': region_label,
            'material_number': m.material_number,
            'sku_label': sku_label,
            'hierarchy_level': m.hierarchy_level,
            'category_code': m.category_code or '',
            'model_type': m.model_type,
            'accuracy': m.accuracy,
            'created_at': m.created_at.astimezone(timezone.get_current_timezone()).strftime('%Y-%m-%d %H:%M') if m.created_at else '',
        })
    return JsonResponse({'success': True, 'models': recent_models})


# ──────────────────────────────────────────────
#  What-If 分析：促销弹性计算
# ──────────────────────────────────────────────

def _calculate_promotion_elasticity(region, material_code, hierarchy_level='sku', category_code=None):
    """从历史 PromotionData + SalesData 计算促销弹性系数。
    
    返回:
      dict: {
        'elasticity': float,          # 弹性系数（1%促销 → N%销量变化）
        'data_available': bool,       # 是否有足够历史数据
        'promo_months': int,          # 有促销数据的月份数
        'baseline_avg': float,        # 无促销时月均销量
        'promo_avg': float,           # 有促销时月均销量
        'promo_mean_strength': float, # 平均促销力度
      }
    """
    # 构建 SalesData 查询条件
    if hierarchy_level == 'sku':
        sales_filter = {
            'sales_region_code': region,
            'product_data__material_number': material_code,
        }
        promo_filter = {
            'sales_region_code': region,
            'product_data__material_number': material_code,
        }
    else:
        field_name = CATEGORY_FIELD_MAP.get(hierarchy_level, 'product_data__product_category_level1')
        sales_filter = {
            'sales_region_code': region,
            field_name: material_code,
        }
        promo_filter = {
            'sales_region_code': region,
            'product_data__' + field_name.replace('product_data__', ''): material_code,
        }

    # 获取月度销量聚合
    from django.db.models import Sum
    from django.db.models.functions import TruncMonth

    monthly_sales = (SalesData.objects
                     .filter(**sales_filter)
                     .annotate(month=TruncMonth('date'))
                     .values('month')
                     .annotate(total_qty=Sum('sales_quantity'))
                     .order_by('month'))

    # 获取促销数据（按月度聚合取平均促销力度）
    monthly_promo = (PromotionData.objects
                     .filter(**promo_filter)
                     .annotate(month=TruncMonth('date'))
                     .values('month')
                     .annotate(avg_strength=Sum('promotion_strength'))
                     .order_by('month'))

    if not monthly_promo.exists():
        return {
            'elasticity': 1.0,
            'data_available': False,
            'promo_months': 0,
            'baseline_avg': 0,
            'promo_avg': 0,
            'promo_mean_strength': 0,
        }

    # 构建 month → (sales, promo_strength) 映射
    sales_map = {s['month'].strftime('%Y-%m'): s['total_qty'] for s in monthly_sales}
    promo_map = {p['month'].strftime('%Y-%m'): p['avg_strength'] for p in monthly_promo}

    # 分类：有促销 vs 无促销
    promo_sales = []
    baseline_sales = []
    promo_strengths = []

    for month, strength in promo_map.items():
        qty = sales_map.get(month, 0)
        if strength is not None and strength > 0.001:
            promo_sales.append(qty)
            promo_strengths.append(strength)
        else:
            baseline_sales.append(qty)

    # 也加入没有促销数据的月份的销量作为基线
    for month, qty in sales_map.items():
        if month not in promo_map:
            baseline_sales.append(qty)

    promo_avg = np.mean(promo_sales) if promo_sales else 0
    baseline_avg = np.mean(baseline_sales) if baseline_sales else 0
    promo_mean_s = np.mean(promo_strengths) if promo_strengths else 0

    if baseline_avg > 0 and promo_avg > 0 and promo_mean_s > 0:
        # 弹性 = (有促销销量/无促销销量 - 1) / 促销力度
        uplift = (promo_avg / baseline_avg) - 1
        elasticity = uplift / promo_mean_s if promo_mean_s > 0 else 1.0
        elasticity = max(0.1, min(5.0, elasticity))  # 限制在合理范围
    else:
        elasticity = 1.0  # 默认：1%促销 → 1%销量变化

    return {
        'elasticity': round(elasticity, 2),
        'data_available': len(promo_sales) >= 2,
        'promo_months': len(promo_sales),
        'baseline_avg': round(baseline_avg, 0),
        'promo_avg': round(promo_avg, 0),
        'promo_mean_strength': round(promo_mean_s, 4),
    }


@login_required
@never_cache
def what_if_analysis(request):
    """What-If 分析：调整促销比例，模拟销量变化"""
    default_start, default_end = _get_sales_date_range()

    # ── 级联分类树（层级字典格式，与 forecast 页面一致）──
    category_tree = _build_category_cascade_tree()

    # ── 区域去重 ──
    raw_regions = SalesData.objects.values_list('sales_region_code', flat=True).distinct()
    regions = sorted(set(r.strip() for r in raw_regions if r and r.strip()))

    # ── SKU→区域 映射（用于级联：选择分类/SKU后过滤可选区域）──
    sku_region_pairs = SalesData.objects.values(
        'product_data__material_number', 'sales_region_code'
    ).distinct()
    sku_regions_map = {}
    for pair in sku_region_pairs:
        sku = pair['product_data__material_number']
        region = (pair['sales_region_code'] or '').strip()
        if sku and region:
            sku_regions_map.setdefault(sku, set()).add(region)
    region_sku_map = {}
    for sku, rset in sku_regions_map.items():
        for r in rset:
            region_sku_map.setdefault(r, set()).add(sku)
    sku_regions_map = {k: sorted(v) for k, v in sku_regions_map.items()}
    region_sku_map = {k: sorted(v) for k, v in region_sku_map.items()}

    # ── 最近训练的模型（供用户参考/选择）──
    recent_models_qs = ForecastModel.objects.order_by('-created_at')[:30]
    recent_models = []
    for m in recent_models_qs:
        region_label = m.sales_region_code
        sku_label = m.material_number
        if m.hierarchy_level == 'sku':
            pd_obj = ProductData.objects.filter(material_number=m.material_number).first()
            if pd_obj and pd_obj.material_name:
                sku_label = f'{m.material_number} | {pd_obj.material_name}'
        else:
            label_key = HIERARCHY_LABEL_MAP.get(m.hierarchy_level, m.hierarchy_level)
            sku_label = f'[{label_key}] {m.material_number}'
        display_name = m.display_name or m.model_name
        recent_models.append({
            'id': m.id,
            'model_name': m.model_name,
            'display_name': display_name,
            'sales_region_code': m.sales_region_code,
            'region_label': region_label,
            'material_number': m.material_number,
            'sku_label': sku_label,
            'hierarchy_level': m.hierarchy_level,
            'category_code': m.category_code or '',
            'model_type': m.model_type,
            'accuracy': round(m.accuracy, 1) if m.accuracy else None,
            'created_at': m.created_at.astimezone(timezone.get_current_timezone()).strftime('%Y-%m-%d %H:%M') if m.created_at else '',
        })

    context = {
        'category_tree': category_tree,
        'regions_list': regions,
        'sku_regions_map': sku_regions_map,
        'region_sku_map': region_sku_map,
        'recent_models': recent_models,
        'recent_models_json': json.dumps(recent_models, ensure_ascii=False, default=str),
        'default_start_date': default_start,
        'default_end_date': default_end,
        'active_tab': 'whatif',
    }

    if request.method == 'POST':
        try:
            region = request.POST.get('region', '').strip()
            hierarchy_level = request.POST.get('hierarchy_level', 'sku')
            item_code = request.POST.get('item_code', '').strip()
            category_code = request.POST.get('category_code', '').strip() or None
            promo_adjust_pct = float(request.POST.get('promo_adjust_pct', 0))
            user_elasticity = request.POST.get('user_elasticity', '').strip()
            forecast_period = int(request.POST.get('forecast_period', 12))
            model_id = request.POST.get('model_id', '').strip() or None

            if not region or not item_code:
                context['error'] = '请选择销售区域和产品'
                return render(request, 'demand_prediction/what_if.html', context)

            if model_id:
                try:
                    model_id = int(model_id)
                except ValueError:
                    model_id = None

            # ── 1. 获取基线预测数据 ──
            try:
                forecast_data = _collect_forecast_data(
                    region, item_code, forecast_period,
                    hierarchy_level=hierarchy_level, category_code=category_code,
                    model_id=model_id
                )
            except ValueError as e:
                context['error'] = str(e)
                return render(request, 'demand_prediction/what_if.html', context)

            # ── 2. 计算促销弹性系数 ──
            elasticity_info = _calculate_promotion_elasticity(
                region, item_code,
                hierarchy_level=hierarchy_level,
                category_code=category_code
            )

            # 用户可覆盖弹性系数
            if user_elasticity:
                try:
                    user_el = float(user_elasticity)
                    if 0.1 <= user_el <= 5.0:
                        elasticity_info['elasticity'] = user_el
                        elasticity_info['user_override'] = True
                except ValueError:
                    pass

            elasticity = elasticity_info['elasticity']

            # ── 3. 计算 What-If 预测 ──
            # sales_change_pct = promo_adjust_pct * elasticity / 100
            # what_if = baseline * (1 + sales_change_pct / 100)
            sales_impact_pct = promo_adjust_pct * elasticity
            impact_multiplier = 1 + sales_impact_pct / 100

            adjusted_results = forecast_data['adjusted_results']
            what_if_results = []
            total_baseline = 0
            total_whatif = 0

            for item in adjusted_results:
                baseline_qty = item['adjusted_forecast']
                what_if_qty = round(baseline_qty * impact_multiplier, 2)
                total_baseline += baseline_qty
                total_whatif += what_if_qty
                what_if_results.append({
                    **item,
                    'what_if_forecast': what_if_qty,
                    'delta': round(what_if_qty - baseline_qty, 2),
                    'delta_pct': round((what_if_qty / baseline_qty - 1) * 100, 1) if baseline_qty > 0 else 0,
                })

            # 图表数据 — 使用 chart_originals 作为完整基线，仅对未来月份施加 what-if 调整
            chart_labels = forecast_data['chart_labels']
            chart_originals = forecast_data['chart_originals']
            chart_future_marker = forecast_data['chart_future']  # 仅用于判断哪些月份是未来

            baseline_combined = []
            what_if_combined = []
            for i in range(len(chart_labels)):
                orig = chart_originals[i]
                is_future = (chart_future_marker[i] is not None)
                if orig is not None:
                    baseline_combined.append(round(orig, 2))
                    if is_future:
                        what_if_combined.append(round(orig * impact_multiplier, 2))
                    else:
                        what_if_combined.append(round(orig, 2))
                else:
                    baseline_combined.append(None)
                    what_if_combined.append(None)

            context.update({
                'result': {
                    'region': region,
                    'item_code': item_code,
                    'hierarchy_level': hierarchy_level,
                    'category_code': category_code,
                    'promo_adjust_pct': promo_adjust_pct,
                    'elasticity': elasticity,
                    'sales_impact_pct': round(sales_impact_pct, 1),
                    'total_baseline': round(total_baseline, 0),
                    'total_whatif': round(total_whatif, 0),
                    'total_delta': round(total_whatif - total_baseline, 0),
                    'total_delta_pct': round((total_whatif / total_baseline - 1) * 100, 1) if total_baseline > 0 else 0,
                    'model_type': forecast_data['model'].model_type,
                    'model_accuracy': round(forecast_data['model'].accuracy, 1),
                },
                'what_if_results': what_if_results,
                'chart_labels_json': json.dumps(chart_labels, ensure_ascii=False),
                'chart_baseline_json': json.dumps(baseline_combined, ensure_ascii=False),
                'chart_whatif_json': json.dumps(what_if_combined, ensure_ascii=False),
                'chart_actuals_json': json.dumps(forecast_data['chart_actuals'], ensure_ascii=False),
                'chart_backtest_json': json.dumps(forecast_data['chart_backtest'], ensure_ascii=False),
                'elasticity_info': elasticity_info,
            })

        except ValueError as e:
            context['error'] = f'参数错误: {e}'
        except Exception as e:
            context['error'] = f'分析失败: {e}'

    return render(request, 'demand_prediction/what_if.html', context)


@login_required
def load_scenario(request, scenario_id):
    """加载预测场景"""
    try:
        scenario = ForecastScenario.objects.get(id=scenario_id)
        forecast_data = _collect_forecast_data(scenario.region, scenario.sku, scenario.forecast_period)
        all_forecasts = []
        for item in forecast_data['adjusted_results']:
            all_forecasts.append({
                'region': scenario.region,
                'sku': scenario.sku,
                **item
            })
        all_chart_data = [{
            'region': scenario.region,
            'sku': scenario.sku,
            'chart_labels': forecast_data['chart_labels'],
            'chart_backtest': forecast_data['chart_backtest'],
            'chart_future': forecast_data['chart_future'],
            'chart_actuals': forecast_data['chart_actuals'],
        }]
        context = {
            'combos': [{'region': scenario.region, 'sku': scenario.sku}],
            'forecasts': all_forecasts,
            'total_combos': 1,
            'scenario_name': scenario.name,
            'model_accuracy': forecast_data['model'].accuracy if forecast_data['model'] else None,
            'all_chart_data_json': json.dumps(all_chart_data, ensure_ascii=False),
            'active_tab': 'forecast'
        }

        return render(request, 'demand_prediction/results.html', context)
    except ForecastScenario.DoesNotExist:
        messages.error(request, _('预测场景不存在'))
        return redirect('forecast:forecast')