#!/usr/bin/env python3
"""QuestieDB (Forever) raw tables -> site/questie/questie.js

Source: https://github.com/Questie/QuestieDB data/Forever/*.lua (fetched into cache/questie/ by hand or by
`python questie.py --fetch`). Each file holds a Lua literal string `[[return { [id] = {...}, ... }]]` whose
positional fields are described by the key tables at the top of the same file.
"""
import json, os, re, sys, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, 'cache', 'questie')
OUT = os.path.join(ROOT, 'site', 'questie')
os.makedirs(CACHE, exist_ok=True)
os.makedirs(OUT, exist_ok=True)
RAW = 'https://raw.githubusercontent.com/Questie/QuestieDB/master/data/Forever/'
FILES = ['foreverQuestDB.lua', 'foreverNpcDB.lua', 'foreverItemDB.lua', 'foreverObjectDB.lua']

META_PATH = os.path.join(CACHE, 'source.json')
if '--fetch' in sys.argv:
    # upstream commit that last touched data/Forever, so the site can say how fresh the data is
    api = 'https://api.github.com/repos/Questie/QuestieDB/commits?path=data/Forever&per_page=1'
    try:
        c = json.loads(urllib.request.urlopen(urllib.request.Request(api, headers={'User-Agent': 'forever-ref'}), timeout=60).read())[0]
        meta = {'commit': c['sha'][:7], 'date': c['commit']['committer']['date'][:10]}
    except Exception as e:
        print('  commit lookup failed:', e)
        meta = {}
    old = json.load(open(META_PATH)) if os.path.exists(META_PATH) else {}
    if meta and meta.get('commit') == old.get('commit') and all(os.path.exists(os.path.join(CACHE, f)) for f in FILES):
        print('  QuestieDB Forever data unchanged at', meta['commit'], meta['date'])
    else:
        for fn in FILES:
            print('  fetch', fn)
            data = urllib.request.urlopen(urllib.request.Request(RAW + fn, headers={'User-Agent': 'forever-ref'}), timeout=120).read()
            open(os.path.join(CACHE, fn), 'wb').write(data)
        if meta:
            json.dump(meta, open(META_PATH, 'w'))
SOURCE_META = json.load(open(META_PATH)) if os.path.exists(META_PATH) else {}

from lupa import lua51
L = lua51.LuaRuntime()


def load_table(fn):
    src = open(os.path.join(CACHE, fn), encoding='utf-8').read()
    keys = {}
    for m in re.finditer(r"^\s*\['(\w+)'\]\s*=\s*(\d+),", src, re.M):
        keys[m.group(1)] = int(m.group(2))
    m = re.search(r"=\s*\[\[(return \{.*)\]\]", src, re.S)
    if not m:
        raise SystemExit(fn + ': data block not found')
    tbl = L.execute(m.group(1))
    return keys, tbl


def conv(v):
    if not hasattr(v, 'items'):
        return v
    ks = list(v.keys())
    if ks and all(isinstance(k, int) for k in ks):
        mx = max(ks)
        if mx <= len(ks) * 2 + 2:   # positional with holes: keep as list with None gaps
            return [conv(v[i]) if i in v else None for i in range(1, mx + 1)]
    return {k: conv(x) for k, x in v.items()}


def rows(fn):
    keys, tbl = load_table(fn)
    idx = {k: i for k, i in keys.items()}
    out = {}
    for id_, entry in tbl.items():
        rec = {}
        for k, i in idx.items():
            val = entry[i]
            if val is not None:
                rec[k] = conv(val)
        out[int(id_)] = rec
    return out


def rnd(p):
    return [round(p[0], 1), round(p[1], 1)]


def spawns(sp, cap=40):
    if not sp:
        return None
    if isinstance(sp, list):   # small zone ids (1, 3, ...) came back positional from conv()
        sp = {i + 1: pts for i, pts in enumerate(sp) if pts}
    out = {}
    for zone, pts in sp.items():
        pts = [rnd(p) for p in (pts or []) if p and p[0] is not None and p[0] >= 0]
        if pts:
            out[int(zone)] = pts[:cap]
    return out or None


print('Parsing QuestieDB Forever tables')
Q = rows('foreverQuestDB.lua')
N = rows('foreverNpcDB.lua')
I = rows('foreverItemDB.lua')
O = rows('foreverObjectDB.lua')
print(f'  quests {len(Q)}, npcs {len(N)}, items {len(I)}, objects {len(O)}')


def lst(v):
    return [x for x in (v or []) if x is not None] if isinstance(v, list) else (list(v.values()) if isinstance(v, dict) else [])


quests = {}
for qid, q in Q.items():
    sb, fb = q.get('startedBy') or [], q.get('finishedBy') or []
    sb = sb + [None] * (3 - len(sb))
    fb = fb + [None] * (2 - len(fb))
    ob = q.get('objectives') or []
    ob = ob + [None] * (6 - len(ob))
    rec = {'n': q.get('name', ''), 'lv': q.get('questLevel') or 0, 'rl': q.get('requiredLevel') or 0}
    for k, src in (('races', 'requiredRaces'), ('classes', 'requiredClasses'), ('zone', 'zoneOrSort'), ('next', 'nextQuestInChain'), ('parent', 'parentQuest'),
                   ('flags', 'questFlags'), ('special', 'specialFlags'), ('srcItem', 'sourceItemId'), ('maxlv', 'requiredMaxLevel'), ('breadcrumbFor', 'breadcrumbForQuestId')):
        if q.get(src):
            rec[k] = q[src]
    st = {k: lst(v) for k, v in (('c', sb[0]), ('o', sb[1]), ('i', sb[2])) if lst(v)}
    en = {k: lst(v) for k, v in (('c', fb[0]), ('o', fb[1])) if lst(v)}
    if st: rec['start'] = st
    if en: rec['end'] = en
    if q.get('objectivesText'): rec['obj'] = ' '.join(x for x in lst(q['objectivesText']) if isinstance(x, str))
    objs = {}
    for k, part in (('c', ob[0]), ('o', ob[1]), ('i', ob[2])):
        items = [[e[0], e[1] if len(e) > 1 and isinstance(e[1], str) else None] for e in lst(part) if isinstance(e, list) and e and e[0]]
        if items: objs[k] = items
    if ob[3] and isinstance(ob[3], list) and len(ob[3]) >= 2: objs['rep'] = [ob[3][0], ob[3][1]]
    if objs: rec['objs'] = objs
    for k, src in (('pre', 'preQuestSingle'), ('preg', 'preQuestGroup'), ('child', 'childQuests'), ('group', 'inGroupWith'), ('excl', 'exclusiveTo'), ('breadcrumbs', 'breadcrumbs')):
        if lst(q.get(src)): rec[k] = lst(q[src])
    if q.get('requiredSkill') and isinstance(q['requiredSkill'], list): rec['skill'] = q['requiredSkill'][:2]
    if q.get('requiredMinRep') and isinstance(q['requiredMinRep'], list): rec['minRep'] = q['requiredMinRep'][:2]
    if q.get('reputationReward'): rec['rep'] = [r[:2] for r in lst(q['reputationReward']) if isinstance(r, list) and len(r) >= 2]
    if q.get('requiredSourceItems'): rec['needItems'] = lst(q['requiredSourceItems'])
    quests[qid] = rec

npcs = {}
for nid, n in N.items():
    rec = {'n': n.get('name', '')}
    for k, src in (('lmin', 'minLevel'), ('lmax', 'maxLevel'), ('rank', 'rank'), ('zone', 'zoneID'), ('sub', 'subName'), ('flags', 'npcFlags'), ('friendly', 'friendlyToFaction'), ('faction', 'factionID')):
        if n.get(src): rec[k] = n[src]
    sp = spawns(n.get('spawns'))
    if sp: rec['spawns'] = sp
    if lst(n.get('questStarts')): rec['qs'] = lst(n['questStarts'])
    if lst(n.get('questEnds')): rec['qe'] = lst(n['questEnds'])
    npcs[nid] = rec

objects = {}
for oid, o in O.items():
    rec = {'n': o.get('name', '')}
    if o.get('zoneID'): rec['zone'] = o['zoneID']
    sp = spawns(o.get('spawns'), 20)
    if sp: rec['spawns'] = sp
    if lst(o.get('questStarts')): rec['qs'] = lst(o['questStarts'])
    if lst(o.get('questEnds')): rec['qe'] = lst(o['questEnds'])
    objects[oid] = rec

items = {}
for iid, it in I.items():
    rec = {}
    for k, src in (('drops', 'npcDrops'), ('odrops', 'objectDrops'), ('idrops', 'itemDrops'), ('vendors', 'vendors'), ('rewardOf', 'questRewards'), ('related', 'relatedQuests')):
        if lst(it.get(src)): rec[k] = lst(it[src])
    if it.get('startQuest'): rec['startQuest'] = it['startQuest']
    if rec:
        rec['n'] = it.get('name', '')
        items[iid] = rec

# reverse index: npc -> items it drops, npc -> items it sells
npcDrops, npcSells = {}, {}
for iid, it in items.items():
    for n in it.get('drops', []): npcDrops.setdefault(n, []).append(iid)
    for n in it.get('vendors', []): npcSells.setdefault(n, []).append(iid)
for nid, lst_ in npcDrops.items():
    if nid in npcs: npcs[nid]['drops'] = lst_
for nid, lst_ in npcSells.items():
    if nid in npcs: npcs[nid]['sells'] = lst_
objDrops = {}
for iid, it in items.items():
    for o in it.get('odrops', []): objDrops.setdefault(o, []).append(iid)
for oid, lst_ in objDrops.items():
    if oid in objects: objects[oid]['drops'] = lst_

out = {'source': 'Questie/QuestieDB data/Forever', 'commit': SOURCE_META.get('commit'), 'date': SOURCE_META.get('date'),
       'quests': quests, 'npcs': npcs, 'objects': objects, 'items': items}
for name, obj in out.items():
    if isinstance(obj, dict):
        json.dump(obj, open(os.path.join(CACHE, name + '.json'), 'w', encoding='utf-8'), ensure_ascii=False)
with open(os.path.join(OUT, 'questie.js'), 'w', encoding='utf-8') as f:
    f.write('window.FR_QUESTIE=' + json.dumps(out, separators=(',', ':'), ensure_ascii=False) + ';\n')
print('wrote site/questie/questie.js', os.path.getsize(os.path.join(OUT, 'questie.js')) // 1024, 'KB')
