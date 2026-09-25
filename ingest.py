#!/usr/bin/env python3
"""Import AlcCollect SavedVariables (collected in-game) into the site.

Reads every WTF/Account/*/SavedVariables/AlcCollect.lua (or files given on the command line, .lua or the
JSON from /alccollect export), keeps a merged copy in cache/collect/merged.json and writes site/collect/collect.js.

Usage: python ingest.py [file ...]
"""
import glob, json, os, sys, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
WTF = r'D:\Games\World of Warcraft\_classic_beta_\WTF\Account'
CACHE = os.path.join(ROOT, 'cache', 'collect')
OUT = os.path.join(ROOT, 'site', 'collect')
os.makedirs(CACHE, exist_ok=True)
os.makedirs(OUT, exist_ok=True)


def lua_to_py(v):
    """lupa table -> dict/list (integer-keyed tables with keys 1..n become lists)."""
    if not hasattr(v, 'items'):
        return v
    keys = list(v.keys())
    if keys and all(isinstance(k, int) for k in keys) and sorted(keys) == list(range(1, len(keys) + 1)):
        return [lua_to_py(v[k]) for k in range(1, len(keys) + 1)]
    return {str(k): lua_to_py(x) for k, x in v.items()}


def load_sv(path):
    if path.endswith('.json'):
        return json.load(open(path, encoding='utf-8'))
    from lupa import lua51
    L = lua51.LuaRuntime()
    L.execute(open(path, encoding='utf-8').read())
    return lua_to_py(L.globals().AlcCollectDB)


def merge(into, db):
    """Merge one character's db into the accumulated store (counts add up, names/positions fill in)."""
    for qid, q in (db.get('quests') or {}).items():
        cur = into['quests'].setdefault(qid, {})
        for k, v in q.items():
            if v is None:
                continue
            if k not in cur or k in ('done', 'acc', 'inlog', 'ender', 'epos', 'rew', 'choice', 'xp', 'money'):
                cur[k] = v
    for src, rec in (db.get('loot') or {}).items():
        cur = into['loot'].setdefault(src, {'seen': 0, 'items': {}})
        cur['seen'] += rec.get('seen', 0)
        cur['coin'] = cur.get('coin', 0) + (rec.get('coin') or 0)
        if rec.get('n'):
            cur['n'] = rec['n']
        for iid, c in (rec.get('items') or {}).items():
            cur['items'][iid] = cur['items'].get(iid, 0) + c
        if rec.get('pos'):
            cur['pos'] = (cur.get('pos') or [])[:0] + rec['pos'][:3]
    for nid, rec in (db.get('npcs') or {}).items():
        cur = into['npcs'].setdefault(nid, {'seen': 0})
        cur['seen'] += rec.get('seen', 0)
        for k in ('n', 'cls', 'ct', 'r'):
            if rec.get(k):
                cur[k] = rec[k]
        if rec.get('lmin'):
            cur['lmin'] = min(cur.get('lmin', rec['lmin']), rec['lmin'])
        if rec.get('lmax'):
            cur['lmax'] = max(cur.get('lmax', rec['lmax']), rec['lmax'])
        if rec.get('pos'):
            cur['pos'] = rec['pos'][:5]
    for key in ('vendors', 'trainers'):
        for nid, rec in (db.get(key) or {}).items():
            cur = into[key].setdefault(nid, {})
            cur.update({k: v for k, v in rec.items() if v is not None})
    into['chars'] = sorted(set(into.get('chars', []) + [f"{(db.get('char') or {}).get('n')}-{(db.get('char') or {}).get('r')}"]))


# ---------------------------------------------------------------- AlcRoute logs -> quest efficiency
def load_route_logs():
    out = []
    # account-wide file (old layout) and per-character files (WTF/Account/<acct>/<realm>/<char>/SavedVariables)
    for fn in glob.glob(os.path.join(WTF, '*', 'SavedVariables', 'AlcRoute.lua')) + glob.glob(os.path.join(WTF, '*', '*', '*', 'SavedVariables', 'AlcRoute.lua')):
        from lupa import lua51
        L = lua51.LuaRuntime()
        L.execute(open(fn, encoding='utf-8').read())
        g = L.globals()
        for var in ('AlcRouteDB', 'AlcRouteChar'):
            d = lua_to_py(g[var]) or {}
            out += [e for e in (d.get('log') or []) if isinstance(e, dict)]
    return out


def efficiency(events):
    """Per quest: turn-in XP, minutes from accept to turn-in (overlapping quests share time, so this is an upper
    bound on the true cost), XP per minute, plus everything gained while the quest was in the log (gx) per
    active minute (ax). Per level: quest XP from turn-ins, and minutes / active minutes / quest-vs-kill split
    from the level-up records (AlcRoute keeps per-level accumulators across sessions). Rate samples: the
    addon's rolling XP/h every 10 minutes, summarised per level."""
    per_quest, per_level, rates = {}, {}, {}

    def lvrec(lv):
        return per_level.setdefault(int(lv), {'xp': 0, 'quests': 0, 'min': 0.0, 'ax': 0.0, 'qx': 0, 'kx': 0})

    for e in sorted(events, key=lambda x: x.get('t') or 0):
        kind = e.get('e')
        if kind == 'turnin' and e.get('q'):
            q = per_quest.setdefault(int(e['q']), {'n': 0, 'xp': 0, 'min': 0.0, 'gx': 0, 'ax': 0.0})
            q['n'] += 1
            q['xp'] += e.get('xp') or 0
            if e.get('dt'):
                q['min'] += min(e['dt'], 3 * 3600) / 60.0
            q['gx'] += e.get('gx') or 0
            q['ax'] += e.get('ax') or 0
            lv = lvrec(e.get('lv') or 0)
            lv['xp'] += e.get('xp') or 0
            lv['quests'] += 1
        elif kind == 'level' and e.get('to'):
            lv = lvrec(int(e['to']) - 1)   # the level just finished
            lv['min'] += (e.get('sec') or 0) / 60.0
            lv['ax'] += e.get('ax') or 0
            lv['qx'] += e.get('qx') or 0
            lv['kx'] += e.get('kx') or 0
        elif kind == 'rate' and e.get('xph'):
            rates.setdefault(int(e.get('lv') or 0), []).append(e['xph'])
    for v in per_level.values():
        total = v['qx'] + v['kx']
        v['xph'] = round(total / (v['ax'] / 60.0)) if v['ax'] >= 5 and total else None
        v['kill'] = round(v['kx'] / total, 3) if total else None
    rate_rows = []
    for lv, xs in sorted(rates.items()):
        xs.sort()
        rate_rows.append({'lv': lv, 'n': len(xs), 'med': xs[len(xs) // 2], 'max': xs[-1]})
    return {'quests': {k: dict(v, xpm=round(v['xp'] / v['min'], 1) if v['min'] else None,
                               gxm=round(v['gx'] / v['ax'], 1) if v['ax'] >= 1 and v['gx'] else None) for k, v in per_quest.items()},
            'levels': per_level, 'rates': rate_rows, 'events': len(events)}


files = sys.argv[1:] or glob.glob(os.path.join(WTF, '*', 'SavedVariables', 'AlcCollect.lua'))
store = {'quests': {}, 'loot': {}, 'npcs': {}, 'vendors': {}, 'trainers': {}, 'chars': []}
merged_path = os.path.join(CACHE, 'merged.json')
if os.path.exists(merged_path):
    store = json.load(open(merged_path, encoding='utf-8'))
for fn in files:
    db = load_sv(fn)
    if not db:
        print('no AlcCollectDB in', fn)
        continue
    merge(store, db)
    print('merged', fn, '| char', (db.get('char') or {}).get('n'))
json.dump(store, open(merged_path, 'w', encoding='utf-8'), ensure_ascii=False)

# ---------------------------------------------------------------- site view
drops = {}      # item -> [[srcKey, count, seen, name]]
for src, rec in store['loot'].items():
    for iid, c in rec['items'].items():
        drops.setdefault(iid, []).append([src, c, rec['seen'], rec.get('n') or store['npcs'].get(src.split(':')[1], {}).get('n', '')])
for lst in drops.values():
    lst.sort(key=lambda x: -x[1])
sold = {}       # item -> [[npcId, price, name]]
for nid, rec in store['vendors'].items():
    for iid, it in (rec.get('items') or {}).items():
        sold.setdefault(iid, []).append([nid, (it or {}).get('p'), rec.get('n', ''), (it or {}).get('na')])
trainers = {}   # service name (lower) -> [[npcId, npcName, skillRank, cost, spellId]]
for nid, rec in store['trainers'].items():
    for name, s in (rec.get('s') or {}).items():
        trainers.setdefault(name.lower(), []).append([nid, rec.get('n', ''), s.get('rank'), s.get('cost'), s.get('sp'), s.get('skill')])
quests = {}
for qid, q in store['quests'].items():
    quests[qid] = {k: q[k] for k in ('t', 'lv', 'giver', 'ender', 'prev', 'item', 'txt', 'obj', 'rew', 'choice', 'xp', 'money', 'gpos', 'epos') if k in q}

route_events = load_route_logs()
eff = efficiency(route_events) if route_events else None
out = {'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), 'chars': store['chars'], 'eff': eff,
       'drops': drops, 'sold': sold, 'trainers': trainers, 'quests': quests, 'npcs': store['npcs'],
       'vendors': {k: {'n': v.get('n'), 'pos': v.get('pos'), 'n_items': len(v.get('items') or {})} for k, v in store['vendors'].items()},
       'loot': {k: {'n': v.get('n'), 'seen': v['seen'], 'items': len(v['items']), 'pos': v.get('pos')} for k, v in store['loot'].items()}}
with open(os.path.join(OUT, 'collect.js'), 'w', encoding='utf-8') as f:
    f.write('window.FR_COLLECT=' + json.dumps(out, separators=(',', ':'), ensure_ascii=False) + ';\n')
print(f"quests {len(quests)}, items with drops {len(drops)}, items sold {len(sold)}, trainer services {len(trainers)}, npcs {len(store['npcs'])}")
