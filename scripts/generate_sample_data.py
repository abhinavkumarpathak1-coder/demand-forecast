#!/usr/bin/env python
"""Generate an anonymised sample dataset for the demand forecast system.

The repository does not ship real customer data. This script creates two Excel
files that follow exactly the layout expected by the upload page:

* ``sales_data.xlsx``      – one row per SKU and month (long format)
* ``promotion_data.xlsx``  – the same rows plus promotion intensity and dates

The series are synthetic but realistic: a mild trend, a monthly seasonal
pattern, promotion spikes and multiplicative noise, so model training, model
selection and the What-If simulation all behave like they do on real data.

Usage::

    python scripts/generate_sample_data.py
    python scripts/generate_sample_data.py --months 48 --start 2020-01 --seed 7
"""

from __future__ import annotations

import argparse
import math
import random
from calendar import monthrange
from datetime import date
from pathlib import Path

import pandas as pd

# (code, name) – fictional regions
REGIONS = [
    ('9001', '示例北区'),
    ('9002', '示例东区'),
    ('9003', '示例南区'),
]

# Region specific volume multiplier
REGION_FACTOR = {'9001': 1.0, '9002': 1.15, '9003': 0.9}

# (category L1..L5, material number, material name, base monthly volume)
CATALOG = [
    ('家居生活', '厨房用品', '餐具', '陶瓷餐具', '6件套', '9000000001', '陶瓷餐具 6件套 白色', 1200),
    ('家居生活', '厨房用品', '餐具', '陶瓷餐具', '12件套', '9000000002', '陶瓷餐具 12件套 米白', 900),
    ('家居生活', '厨房用品', '锅具', '不粘锅', '28cm', '9000000003', '不粘炒锅 28cm', 600),
    ('家居生活', '厨房用品', '锅具', '不锈钢锅', '24cm', '9000000004', '不锈钢汤锅 24cm', 450),
    ('家居生活', '收纳整理', '收纳箱', '布艺收纳箱', '大号', '9000000005', '布艺收纳箱 大号 灰色', 800),
    ('家居生活', '收纳整理', '收纳箱', '塑料收纳箱', '中号', '9000000006', '塑料收纳箱 中号 透明', 650),
    ('家居生活', '清洁用品', '拖把', '平板拖把', '标准装', '9000000007', '平板拖把 标准装', 520),
    ('家居生活', '清洁用品', '清洁剂', '多效清洁剂', '500ml', '9000000008', '多效清洁剂 500ml', 430),
    ('家居生活', '清洁用品', '清洁剂', '玻璃清洁剂', '500ml', '9000000009', '玻璃清洁剂 500ml', 380),
]

# Jan .. Dec seasonal factors
SEASONALITY = [0.85, 0.80, 0.95, 1.00, 1.05, 1.10, 1.15, 1.10, 1.05, 1.00, 0.95, 0.90]

# Promotion elasticity used to generate the promotion lift
ELASTICITY = 2.2

SALES_COLUMNS = [
    '销售区域代码', '销售区域名称', '产品一级分类', '产品二级分类', '产品三级分类',
    '产品四级分类', '产品五级分类', '物料号', '物料名称', '日期', '销量',
]

PROMOTION_COLUMNS = [
    '销售区域代码', '销售区域名称', '产品一级分类', '产品二级分类', '产品三级分类',
    '产品四级分类', '产品五级分类', '物料号', '物料名称', '日期',
    '促销力度', '促销开始日期', '促销结束日期',
]


def month_range(start: date, months: int):
    """Yield (year, month) tuples starting at *start* for *months* months."""
    year, month = start.year, start.month
    for _ in range(months):
        yield year, month
        month += 1
        if month > 12:
            month = 1
            year += 1


def build_rows(start: date, months: int, rng: random.Random):
    sales_rows = []
    promotion_rows = []

    for index, (year, month) in enumerate(month_range(start, months)):
        first_day = date(year, month, 1)
        last_day = date(year, month, monthrange(year, month)[1])
        progress = index / max(months - 1, 1)

        for region_code, region_name in REGIONS:
            for (l1, l2, l3, l4, l5, material, name, base) in CATALOG:
                seasonal = SEASONALITY[month - 1]
                trend = 1.0 + 0.18 * progress
                noise = math.exp(rng.gauss(0, 0.06))

                # Roughly one month in four runs a promotion for this SKU.
                if rng.random() < 0.25:
                    strength = round(rng.uniform(0.08, 0.25), 2)
                else:
                    strength = 0.0

                lift = 1.0 + ELASTICITY * strength
                volume = base * REGION_FACTOR[region_code] * seasonal * trend * lift * noise
                volume = int(round(volume / 10.0) * 10)

                common = {
                    '销售区域代码': region_code,
                    '销售区域名称': region_name,
                    '产品一级分类': l1,
                    '产品二级分类': l2,
                    '产品三级分类': l3,
                    '产品四级分类': l4,
                    '产品五级分类': l5,
                    '物料号': material,
                    '物料名称': name,
                    '日期': first_day.strftime('%Y-%m-%d'),
                }
                sales_rows.append(dict(common, 销量=volume))
                promotion_rows.append(dict(
                    common,
                    促销力度=strength,
                    促销开始日期=first_day.strftime('%Y-%m-%d') if strength else '',
                    促销结束日期=last_day.strftime('%Y-%m-%d') if strength else '',
                ))

    return sales_rows, promotion_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--months', type=int, default=36, help='number of months to generate (default: 36)')
    parser.add_argument('--start', default='2021-01', help='first month, YYYY-MM (default: 2021-01)')
    parser.add_argument('--seed', type=int, default=42, help='random seed for reproducible output')
    parser.add_argument('--output-dir', default='TestData', help='target directory (default: TestData)')
    args = parser.parse_args()

    if args.months < 12:
        parser.error('--months must be at least 12, otherwise seasonality cannot be learned')

    year, month = (int(part) for part in args.start.split('-'))
    start = date(year, month, 1)

    rng = random.Random(args.seed)
    sales_rows, promotion_rows = build_rows(start, args.months, rng)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sales_path = output_dir / 'sales_data.xlsx'
    promotion_path = output_dir / 'promotion_data.xlsx'
    pd.DataFrame(sales_rows, columns=SALES_COLUMNS).to_excel(sales_path, index=False)
    pd.DataFrame(promotion_rows, columns=PROMOTION_COLUMNS).to_excel(promotion_path, index=False)

    last_month = list(month_range(start, args.months))[-1]
    print(f'{args.months} months, {len(REGIONS)} regions, {len(CATALOG)} SKUs '
          f'({start:%Y-%m} .. {last_month[0]}-{last_month[1]:02d})')
    print(f'  {sales_path}      {len(sales_rows)} rows')
    print(f'  {promotion_path}  {len(promotion_rows)} rows')
    print('Upload both files from the Data Management page.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
