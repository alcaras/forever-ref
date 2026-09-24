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

DARKMOON = {f for f, n in factions.items() if n == 'Darkmoon Faire'}
RACES = {int(r['ID']): r['Name_lang'] for r in csv.DictReader(open(os.path.join(ROOT, 'cache', BUILD, 'ChrRaces.csv'), encoding='utf-8', newline=''))} \
    if os.path.exists(os.path.join(ROOT, 'cache', BUILD, 'ChrRaces.csv')) else {}
chains_path = os.path.join(ROOT, 'cache', 'wowhead', 'quest-chains.json')
chains = json.load(open(chains_path, encoding='utf-8')) if os.path.exists(chains_path) else {}
info_path = os.path.join(ROOT, 'cache', 'wowhead', 'quest-info.json')   # quick facts: Start / End NPC, class, race
info = json.load(open(info_path, encoding='utf-8')) if os.path.exists(info_path) else {}
desc_path = os.path.join(ROOT, 'cache', 'wowhead', 'quest-desc.json')   # description text, only for quests with no recorded starter
descs = json.load(open(desc_path, encoding='utf-8')) if os.path.exists(desc_path) else {}

# Wowhead has no faction flag (side 0) on these; inferred from the quest giver / turn-in NPC. 1 Alliance, 2 Horde, 3 both.
SIDE_OVERRIDES = {
    95204: 2,   # Crest of Lordaeron -> Oran Snakewrithe (Undercity)
    92422: 2,   # The Wrath of Rath'mael -> Deathguard Kristof (Undercity)
    4003: 2,    # The Royal Rescue: Thrall
    4004: 2,    # The Princess Saved?: Thrall
    96393: 1,   # Old Ironforge Incursion -> King Magni Bronzebeard
    1500: 3,    # Waking Naralex (Naralex's Disciple, neutral)
    999: 3,     # When Dreams Turn to Nightmares
    3911: 3,    # The Last Element
    7462: 3,    # The Treasure of the Shen'dralar
    7703: 3,    # Unfinished Gordok Business: Captain Kromcrush
    7487: 3,    # Attunement to the Core
    85558: 3,   # Commit to Quality: Master Elemental Shaper Krixix
    85557: 3,   # Efficiency Is Priority One: Krixix
}

dungeons = []
used_factions = set()
for z in ORDER:
    e = raw.get(str(z))
    if not e:
        continue
    name = NAMES.get(z) or e.get('title', '').replace(' - Zone - Forever', '').strip() or str(z)
    quests = []
    for q in e.get('quests') or []:
        if any(f in DARKMOON for f, _ in (q.get('reprewards') or [])) or 'Fortune Awaits' in q['name']:   # Darkmoon Faire fortune quests are listed under every dungeon
            continue
        rec = {'id': q['id'], 'n': q['name'], 'lv': q.get('level') or 0, 'rl': q.get('reqlevel') or 0, 'side': q.get('side') or 0,
               'xp': q.get('xp') or 0, 'type': q.get('type') or 0}
        if not rec['side'] and q['id'] in SIDE_OVERRIDES:
            rec['side'] = SIDE_OVERRIDES[q['id']]
            rec['inf'] = 1
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
        qi = info.get(str(q['id'])) or {}
        for k in ('start', 'end'):
            if qi.get(k):
                rec[k] = qi[k]          # [[npc|object|item, id, name], ...]
        if not qi.get('start') and descs.get(str(q['id'])):
            rec['desc'] = descs[str(q['id'])][:300]
        if qi.get('cls'):
            rec['cls'] = qi['cls']
        if qi.get('race'):
            rec['race'] = qi['race']
        ch = chains.get(str(q['id']))
        if ch and ch != 'ERR' and isinstance(ch, list) and len(ch) > 1:
            rec['chain'] = ch   # [[step label, [[questId, name], ...]], ...] from the Wowhead "Series" box
        quests.append(rec)
    quests.sort(key=lambda q: (q['lv'], q['n']))
    dungeons.append({'zone': z, 'n': name, 'kind': 'raid' if z in RAIDS else 'dungeon', 'quests': quests,
                     'nodata': e.get('quests') is None})

# Reward items that are not in the Forever client tables: look their names up on Wowhead's tooltip endpoint (cached).
import json as _json, re, html as _html, time, urllib.request
site_items = _json.loads(open(os.path.join(ROOT, 'site', 'data', 'items.js'), encoding='utf-8').read()[len('window.FR_ITEMS='):-2])
missing = sorted({r[0] for d in dungeons for q in d['quests'] for r in (q.get('rew') or []) + (q.get('choice') or []) if str(r[0]) not in site_items})
cache_path = os.path.join(ROOT, 'cache', 'wowhead', 'items.json')
extra = _json.load(open(cache_path, encoding='utf-8')) if os.path.exists(cache_path) else {}
for iid in missing:
    if str(iid) in extra:
        continue
    try:
        d = _json.loads(urllib.request.urlopen(urllib.request.Request(f'https://nether.wowhead.com/forever/tooltip/item/{iid}', headers={'User-Agent': 'Mozilla/5.0 forever-ref'}), timeout=30).read())
        extra[str(iid)] = {'n': _html.unescape(d.get('name', '')), 'q': int(d.get('quality', 1)), 'ic': d.get('icon', '')}
    except Exception as e:
        extra[str(iid)] = {'n': '', 'q': 1, 'ic': ''}
        print('  tooltip failed', iid, e)
    time.sleep(0.3)
_json.dump(extra, open(cache_path, 'w', encoding='utf-8'), ensure_ascii=False)
print(f'{len(missing)} reward items not in the client, names from Wowhead')

out = {'source': 'wowhead.com/forever zone pages', 'items': {k: v for k, v in extra.items() if int(k) in missing and v['n']}, 'harvested': os.path.getmtime(SRC) and __import__('datetime').datetime.fromtimestamp(os.path.getmtime(SRC)).strftime('%Y-%m-%d'),
       'dungeons': dungeons, 'factions': {f: factions.get(f, '#%d' % f) for f in sorted(used_factions)}}
with open(os.path.join(OUT, 'quests.js'), 'w', encoding='utf-8') as f:
    f.write('window.FR_QUESTS=' + json.dumps(out, separators=(',', ':'), ensure_ascii=False) + ';\n')
n = sum(len(d['quests']) for d in dungeons)
horde = sum(1 for d in dungeons for q in d['quests'] if q['side'] in (2, 3))
print(f'{len(dungeons)} instances, {n} quests ({horde} Horde-available), {sum(1 for d in dungeons if d["nodata"])} without Wowhead data')
