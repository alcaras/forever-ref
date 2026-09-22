#!/usr/bin/env python3
"""Compare generated item data with Wowhead Forever tooltips for a sample of items.

Usage: python validate.py [itemId ...]   (default: a built-in sample covering every stat kind)
"""
import json, re, sys, time, html, urllib.request, collections

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) forever-ref validator'}
items = json.loads(open('site/data/items.js', encoding='utf-8').read()[len('window.FR_ITEMS='):-2])
meta = json.loads(open('site/data/meta.js', encoding='utf-8').read()[len('window.FR_META='):-2])


def wowhead(iid):
    url = f'https://nether.wowhead.com/forever/tooltip/item/{iid}'
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read())
    t = re.sub(r'<br\s*/?>', '\n', d.get('tooltip', ''))
    t = re.sub(r'</(div|tr|td|table)>', '\n', t)
    t = html.unescape(re.sub(r'<[^>]+>', '', t))
    return [ln.strip() for ln in t.split('\n') if ln.strip()]


def mine(iid):
    it = items[str(iid)]
    out = [it['n'], f"ilvl {it['il']} q{it['q']} slot {meta['invTypes'].get(str(it['it']), '')} class {it['c']}/{it['sc']}"]
    if it.get('dm'):
        out.append('dmg ' + json.dumps(it['dm']))
    if it.get('ar'):
        out.append(f"armor {it['ar']}")
    for st, v in it.get('s', []):
        out.append(f"stat {st} {meta['stats'].get(str(st), '?')} = {v}")
    if it.get('rl'):
        out.append(f"req level {it['rl']}")
    if it.get('sp'):
        out.append(f"sell {it['sp']}")
    return out


if len(sys.argv) > 1:
    sample = [int(a) for a in sys.argv[1:]]
else:
    sample = [12640, 19019, 12784, 2679, 2697, 19351, 18348, 11307, 13340, 2140, 19321, 4975, 16846]
    wanted = [12, 13, 14, 15, 36, 37, 38, 39, 41, 42, 43, 44, 45, 46, 47, 48, 50, 83, 84, 85, 86, 87, 88, 89, 90, 96, 117, 124, 127, 128, 131]
    for w in wanted:
        ex = [int(k) for k, v in items.items() if any(st == w for st, _ in v.get('s', [])) and not v['n'].lower().startswith('test')]
        if ex:
            sample.append(ex[len(ex) // 2])
    seen = set()
    sample = [s for s in sample if not (s in seen or seen.add(s))]

for iid in sample:
    print('=' * 100)
    try:
        wh = wowhead(iid)
    except Exception as e:
        wh = ['ERROR ' + str(e)]
    if str(iid) not in items:
        print("missing", iid); continue
    a, b = mine(iid), wh
    for i in range(max(len(a), len(b))):
        print('%-58s | %s' % (a[i] if i < len(a) else '', b[i] if i < len(b) else ''))
    time.sleep(0.4)
