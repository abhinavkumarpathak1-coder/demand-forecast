#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Rebuild the Simplified Chinese catalog from the English one.

The UI source strings are Chinese, so ``locale/zh_Hans`` is an identity
catalog (``msgstr == msgid``). It must exist, otherwise Django falls back to
the default (English) catalog and the Chinese UI would show English text.

Usage (from the project root)::

    python scripts/sync_zh_catalog.py

Run it after ``python manage.py makemessages -l en -l zh_Hans``.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE_DIR, 'locale', 'en', 'LC_MESSAGES', 'django.po')
DST_DIR = os.path.join(BASE_DIR, 'locale', 'zh_Hans', 'LC_MESSAGES')
DST = os.path.join(DST_DIR, 'django.po')

HEADER_REPLACEMENTS = [
    ('# English translation of the Demand Forecast System.',
     '# Simplified Chinese translation of the Demand Forecast System.'),
    ('"Language-Team: English\\n"', '"Language-Team: Chinese (Simplified)\\n"'),
    ('"Language: en\\n"', '"Language: zh_Hans\\n"'),
]


def po_escape(text):
    return text.replace('\\', '\\\\').replace('"', '\\"')


def main():
    if not os.path.exists(SRC):
        sys.exit('Source catalog not found: %s' % SRC)

    with open(SRC, encoding='utf-8') as fh:
        lines = fh.read().split('\n')

    out = []
    current = None
    count = 0
    for line in lines:
        if line.startswith('msgid '):
            current = line[6:].strip()
            out.append(line)
        elif current is not None and line.startswith('"'):
            current = current[:-1] + line.strip()[1:-1] + '"'
            out.append(line)
        elif line.startswith('msgstr ') and current is not None:
            msgid = current[1:-1]
            if msgid == '':
                out.append(line)
            else:
                out.append('msgstr "%s"' % po_escape(msgid))
                count += 1
            current = None
        else:
            out.append(line)

    text = '\n'.join(out)
    for old, new in HEADER_REPLACEMENTS:
        text = text.replace(old, new)

    os.makedirs(DST_DIR, exist_ok=True)
    with open(DST, 'w', encoding='utf-8') as fh:
        fh.write(text)
    print('Wrote %s (%d entries). Now run: python manage.py compilemessages' % (DST, count))


if __name__ == '__main__':
    main()
