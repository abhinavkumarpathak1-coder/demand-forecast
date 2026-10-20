from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Min, Max
from apps.data_management.models import SalesData, ProductData
from datetime import datetime, timedelta
from django.http import JsonResponse
import json
import pandas as pd


@login_required
def index(request):
    # 数据库中的日期范围（用于默认值）
    date_range = SalesData.objects.aggregate(
        min_date=Min('date'),
        max_date=Max('date')
    )
    db_min_date = date_range['min_date']
    db_max_date = date_range['max_date']
    default_start = db_min_date.strftime('%Y-%m-%d') if db_min_date else ''
    default_end = db_max_date.strftime('%Y-%m-%d') if db_max_date else ''

    # filters
    regions = request.GET.getlist('region')
    skus = request.GET.getlist('sku')
    start_date = request.GET.get('start_date', default_start)
    end_date = request.GET.get('end_date', default_end)
    chart_skus = request.GET.getlist('chart_sku')
    time_unit = request.GET.get('time_unit', 'month')  # year, quarter, month, week

    qs = SalesData.objects.select_related('product_data').all()
    if regions:
        qs = qs.filter(sales_region_code__in=regions)
    if skus:
        qs = qs.filter(product_data__material_number__in=skus)
    if start_date:
        try:
            sd = datetime.strptime(start_date, '%Y-%m-%d').date()
            qs = qs.filter(date__gte=sd)
        except Exception:
            sd = None
    else:
        sd = None
    if end_date:
        try:
            ed = datetime.strptime(end_date, '%Y-%m-%d').date()
            qs = qs.filter(date__lte=ed)
        except Exception:
            ed = None
    else:
        ed = None

    # Top5 regions by sales
    region_agg = qs.values('sales_region_code').annotate(total=Sum('sales_quantity')).order_by('-total')[:5]
    top_regions = [r['sales_region_code'] or '未知' for r in region_agg]
    top_regions_values = [float(r['total'] or 0) for r in region_agg]

    # Top5 SKUs overall
    sku_agg = qs.values('product_data__material_number').annotate(total=Sum('sales_quantity')).order_by('-total')[:5]
    top_skus = [s['product_data__material_number'] or '未知' for s in sku_agg]
    top_skus_values = [float(s['total'] or 0) for s in sku_agg]

    # For top regions, compute per-region Top5 SKUs (for drill-down modal)
    top_region_skus_map = {}
    if top_regions:
        for region_code in top_regions:
            region_sku_qs = qs.filter(sales_region_code=region_code)
            reg_sku_agg = region_sku_qs.values('product_data__material_number').annotate(
                total=Sum('sales_quantity')
            ).order_by('-total')[:5]
            top_region_skus_map[region_code] = {
                'skus': [r['product_data__material_number'] or '未知' for r in reg_sku_agg],
                'values': [float(r['total'] or 0) for r in reg_sku_agg]
            }

    # For top SKUs, compute per-SKU Top5 regions (for drill-down modal)
    top_sku_regions_map = {}
    if top_skus:
        for sku_code in top_skus:
            sku_region_qs = qs.filter(product_data__material_number=sku_code)
            sku_reg_agg = sku_region_qs.values('sales_region_code').annotate(
                total=Sum('sales_quantity')
            ).order_by('-total')[:5]
            top_sku_regions_map[sku_code] = {
                'regions': [r['sales_region_code'] or '未知' for r in sku_reg_agg],
                'values': [float(r['total'] or 0) for r in sku_reg_agg]
            }

    # all available regions and skus for filter dropdowns (strip and deduplicate)
    all_regions_raw = SalesData.objects.values_list('sales_region_code', flat=True).distinct()
    all_regions = sorted(set(r.strip() if r else '' for r in all_regions_raw if r and r.strip()))
    all_skus_raw = ProductData.objects.values_list('material_number', flat=True).distinct()
    all_skus = sorted(set(s.strip() if s else '' for s in all_skus_raw if s and s.strip()))

    # region→skus mapping for client-side filtering (JSON)
    region_sku_pairs = SalesData.objects.values(
        'sales_region_code', 'product_data__material_number'
    ).distinct()
    region_sku_map = {}
    for pair in region_sku_pairs:
        reg = (pair['sales_region_code'] or '').strip()
        sku = (pair['product_data__material_number'] or '').strip()
        if not reg or not sku:
            continue
        region_sku_map.setdefault(reg, []).append(sku)
    # deduplicate and sort
    for reg in region_sku_map:
        region_sku_map[reg] = sorted(set(region_sku_map[reg]))

    # prepare trend data for chosen SKUs
    trend_labels = []
    trend_datasets = []
    if chart_skus:
        chart_qs = qs.filter(product_data__material_number__in=chart_skus).values_list(
            'date', 'product_data__material_number', 'sales_quantity'
        )
        df = None
        try:
            df = pd.DataFrame(list(chart_qs), columns=['date', 'sku', 'sales_quantity'])
        except Exception:
            df = None
        if df is not None and not df.empty:
            df['date'] = pd.to_datetime(df['date'])
            df = df.set_index('date')
            freq_map = {
                'year': 'Y',
                'quarter': 'Q',
                'month': 'M',
                'week': 'W'
            }
            rule = freq_map.get(time_unit, 'M')
            grouped = df.groupby('sku').resample(rule)['sales_quantity'].sum().unstack(level=0).fillna(0)
            trend_labels = [
                d.strftime('%Y-%m') if time_unit in ['month', 'quarter'] else d.strftime('%Y') if time_unit == 'year' else d.strftime('%Y-%W')
                for d in grouped.index
            ]
            for sku in grouped.columns:
                trend_datasets.append({
                    'label': sku,
                    'data': [float(x) for x in grouped[sku].tolist()]
                })

    context = {
        'regions': all_regions,
        'skus': all_skus,
        'region_sku_map_json': json.dumps(region_sku_map, ensure_ascii=False),
        'top_region_skus_map_json': json.dumps(top_region_skus_map, ensure_ascii=False),
        'top_sku_regions_map_json': json.dumps(top_sku_regions_map, ensure_ascii=False),
        'selected_regions': request.GET.getlist('region'),
        'selected_skus': request.GET.getlist('sku'),
        'start_date': start_date,
        'end_date': end_date,
        'selected_chart_skus': chart_skus,
        'time_unit': time_unit,
        # 使用 json.dumps 序列化为合法 JSON，避免 Python repr 注入 JS 时报错
        'top_regions': json.dumps(top_regions, ensure_ascii=False),
        'top_regions_values': json.dumps(top_regions_values, ensure_ascii=False),
        'top_skus': json.dumps(top_skus, ensure_ascii=False),
        'top_skus_values': json.dumps(top_skus_values, ensure_ascii=False),
        'trend_labels': json.dumps(trend_labels, ensure_ascii=False),
        'trend_datasets': json.dumps(trend_datasets, ensure_ascii=False),
    }
    return render(request, 'data_insight/index.html', context)

