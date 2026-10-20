"""Locale aware date formatting for templates.

`strftime()` always produces language neutral output such as ``2025-01``, so a
Chinese page would still show dates in a numeric, English-looking format.
These filters render dates with the active locale (Django's own catalogs supply
the month names and date formats).
"""
import datetime

from django import template
from django.utils import formats
from django.utils.translation import gettext

register = template.Library()

# Language specific pattern for a "year + month" label (see localize_month).
# Each translation picks either #month_name# (January / janvier) or
# #month_num# (1): 中文 "2025年1月", English "January 2025", 日本語 "2025年1月".
# Tokens are used instead of {} because msgfmt would otherwise treat the entry
# as a brace format and reject translations that use the other variable.

_PARSE_FORMATS = ('%Y-%m-%d', '%Y-%m', '%Y/%m/%d', '%Y/%m', '%Y%m')


def _to_date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value or '').strip()
    for fmt in _PARSE_FORMATS:
        for candidate in (text, text[:10], text[:7]):
            try:
                return datetime.datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


@register.filter
def localize_date(value):
    """Render a date with the locale's DATE_FORMAT (e.g. 2025年1月1日 / Jan. 1, 2025)."""
    date_value = _to_date(value)
    if date_value is None:
        return value
    return formats.date_format(date_value, 'DATE_FORMAT')


@register.filter
def localize_month(value):
    """Render a month with the locale's month name (e.g. 2025年1月 / January 2025)."""
    date_value = _to_date(value)
    if date_value is None:
        return value
    pattern = gettext('#year#年#month_num#月')
    for token, value in (
        ('#year#', formats.date_format(date_value, 'Y')),
        ('#month_name#', formats.date_format(date_value, 'F')),
        ('#month_num#', formats.date_format(date_value, 'n')),
    ):
        pattern = pattern.replace(token, value)
    return pattern
