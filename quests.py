#!/usr/bin/env python3
"""Dungeon quest lists -> site/quests/quests.js

Quests are server-side and not in the client, so this reads Wowhead Forever's per-zone quest listviews,
harvested through the browser into cache/wowhead/dungeon-quests.json (see tools/recv.py for how).
Faction names for reputation rewards come from the client's Faction table.
"""
import csv, json, os

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, 'cache', 'wowhead', 'dungeon-quests.json')
OUT = os.path.join(ROOT, 'site', 'quests')
os.makedirs(OUT, exist_ok=True)
BUILD = open(os.path.join(ROOT, 'builds', 'LATEST')).read().strip()

RAIDS = {2159, 2717, 2677, 1977, 3429, 3428, 3456, 15531, 15532, 15825, 16003, 16236, 956}
NAMES = {1477: "Sunken Temple (Temple of Atal'Hakkar)", 3428: "Temple of Ahn'Qiraj", 15938: 'Starfall Barrow Den',
         16003: 'Nightmare Grove', 956: 'Emerald Dream'}
ORDER = [2437, 718, 1581, 209, 719, 717, 721, 491, 796, 722, 1337, 1176, 2100, 1477, 1584, 1583, 2557, 2017, 2057,
         16611, 16919, 15475, 16362, 15828, 15938, 16074, 16295, 16394, 16544, 16732, 16632, 17191,
         2159, 2717, 2677, 1977, 3429, 3428, 3456, 15531, 15532, 15825, 16003, 16236, 956]

raw = json.load(open(SRC, encoding='utf-8'))
factions = {}
for r in csv.DictReader(open(os.path.join(ROOT, 'cache', BUILD, 'Faction.csv'), encoding='utf-8', newline='')):
    factions[int(r['ID'])] = r['Name_lang']

dungeons = []
used_factions = set()
for z in ORDER:
    e = raw.get(str(z))
    if not e:
        continue
    name = NAMES.get(z) or e.get('title', '').replace(' - Zone - Forever', '').strip() or str(z)
    quests = []
    for q in e.get('quests') or []:
        rec = {'id': q['id'], 'n': q['name'], 'lv': q.get('level') or 0, 'rl': q.get('reqlevel') or 0, 'side': q.get('side') or 0,
               'xp': q.get('xp') or 0, 'type': q.get('type') or 0}
        if q.get('money'):
            rec['money'] = q['money']
        if q.get('itemrewards'):
            rec['rew'] = q['itemrewards']
        if q.get('itemchoices'):
            rec['choice'] = q['itemchoices']
        if q.get('reprewards'):
            rec['rep'] = q['reprewards']
            for f, _ in q['reprewards']:
                used_factions.add(f)
        env = q.get('env') or {}
        if env.get('lines'):
            rec['chg'] = env['lines']
        quests.append(rec)
    quests.sort(key=lambda q: (q['lv'], q['n']))
    dungeons.append({'zone': z, 'n': name, 'kind': 'raid' if z in RAIDS else 'dungeon', 'quests': quests,
                     'nodata': e.get('quests') is None})

out = {'source': 'wowhead.com/forever zone pages', 'harvested': os.path.getmtime(SRC) and __import__('datetime').datetime.fromtimestamp(os.path.getmtime(SRC)).strftime('%Y-%m-%d'),
       'dungeons': dungeons, 'factions': {f: factions.get(f, '#%d' % f) for f in sorted(used_factions)}}
with open(os.path.join(OUT, 'quests.js'), 'w', encoding='utf-8') as f:
    f.write('window.FR_QUESTS=' + json.dumps(out, separators=(',', ':'), ensure_ascii=False) + ';\n')
n = sum(len(d['quests']) for d in dungeons)
horde = sum(1 for d in dungeons for q in d['quests'] if q['side'] in (2, 3))
print(f'{len(dungeons)} instances, {n} quests ({horde} Horde-available), {sum(1 for d in dungeons if d["nodata"])} without Wowhead data')
