#!/usr/bin/env python3
"""Leveling route planner for a Horde 5-man on WoW Forever.

Policy: quest solo along a route; each dungeon is run exactly once, at the first level where the group can
hold every quest for it (gate level = highest required level among the dungeon's quests and their
prerequisites) and the mobs are doable. Prerequisite chains are pulled forward so they are done before
that level. The 1-22 backbone is imported from RestedXP's free Forever Horde guides; the rest is generated
greedily from QuestieDB (prerequisites, positions) and Wowhead (dungeon quest lists, XP).

Inputs (already produced by other scripts): cache/questie/{quests,npcs,items}.json, cache/questie/xpDB-classic.lua,
site/quests/quests.js, site/maps/maps.js, cache/maps/UiMapAssignment.csv, RXPGuides Forever Horde guides.
Output: site/route/route.js and a console summary.

Usage: python route.py [--start durotar|tirisfal|mulgore] [--class Warrior] [--mob-margin N]
"""
import csv, glob, json, math, os, re, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
QC = os.path.join(ROOT, 'cache', 'questie')
OUT = os.path.join(ROOT, 'site', 'route')
os.makedirs(OUT, exist_ok=True)
RXP = r'D:\Games\World of Warcraft\_classic_beta_\Interface\AddOns\RXPGuides\Guides\Forever'
ARG = sys.argv
START = ARG[ARG.index('--start') + 1] if '--start' in ARG else 'durotar'
CLASS = ARG[ARG.index('--class') + 1] if '--class' in ARG else 'Warrior'
MOB_MARGIN = int(ARG[ARG.index('--mob-margin') + 1]) if '--mob-margin' in ARG else 0
MAX_LEVEL = 60

# Classic XP needed to go from level L to L+1 (index L-1)
XP_TO_NEXT = [400, 900, 1400, 2100, 2800, 3600, 4500, 5400, 6500, 7600, 8700, 9800, 11000, 12300, 13600, 15000, 16400, 17800, 19300, 20800,
              22400, 24000, 25500, 27200, 28900, 30500, 32200, 33900, 36300, 38800, 41600, 44600, 48000, 51400, 55000, 58700, 62400, 66200, 70200, 74300,
              78500, 82800, 87100, 91600, 96300, 101000, 105800, 110700, 115700, 120900, 126100, 131500, 137000, 142500, 148200, 154000, 159900, 165800, 171800]
RACE_H = 2 + 16 + 32 + 128
CLASS_BITS = {'Warrior': 1, 'Paladin': 2, 'Hunter': 4, 'Rogue': 8, 'Priest': 16, 'Shaman': 64, 'Mage': 128, 'Warlock': 256, 'Druid': 1024}
KILL_XP_FRACTION = 0.45      # XP from kills while doing a quest, as a fraction of the quest's XP (Classic experience)
RUN_SPEED = 7.0              # yards per second on foot
MOUNT_LEVEL, MOUNT_SPEED = 40, 11.2
ZONE_HOP = 240.0             # seconds for a zone change (flight or ride) on top of in-zone travel
OBJECTIVE_TIME = {'c': 150.0, 'o': 60.0, 'i': 150.0, 'rep': 300.0}
DUNGEON_TIME = 75 * 60.0
DUNGEON_ZONE_ALIASES = {1584: [1584, 1585]}   # QuestieDB keys Blackrock Depths NPCs on 1585; Wowhead's zone is 1584

# ---------------------------------------------------------------- data
def loadjs(path, var):
    s = open(path, encoding='utf-8').read()
    return json.loads(s[len('window.%s=' % var):-2])


Q = {int(k): v for k, v in json.load(open(os.path.join(QC, 'quests.json'), encoding='utf-8')).items()}
N = {int(k): v for k, v in json.load(open(os.path.join(QC, 'npcs.json'), encoding='utf-8')).items()}
WQ = loadjs(os.path.join(ROOT, 'site', 'quests', 'quests.js'), 'FR_QUESTS')
MAPS = loadjs(os.path.join(ROOT, 'site', 'maps', 'maps.js'), 'FR_MAPS')['maps']
ZONES = loadjs(os.path.join(ROOT, 'site', 'data', 'zones.js'), 'FR_ZONES')
ZNAME = {z['id']: z['n'] for z in ZONES['zones']}
XP = {}
for m in re.finditer(r'\[(\d+)\]\s*=\s*\{(\d+),\s*(\d+)\}', open(os.path.join(QC, 'xpDB-classic.lua'), encoding='utf-8').read()):
    XP[int(m.group(1))] = (int(m.group(2)), int(m.group(3)))
WHQ = {}
for d in WQ['dungeons']:
    for q in d['quests']:
        WHQ[q['id']] = dict(q, dungeon=d['zone'], dname=d['n'])
AREA_TO_MAP = {m['area']: int(mid) for mid, m in MAPS.items() if m.get('area')}
# zone size in yards from the client's UiMapAssignment regions
ZONE_YARDS = {}
for r in csv.DictReader(open(os.path.join(ROOT, 'cache', 'maps', 'UiMapAssignment.csv'), encoding='utf-8', newline='')):
    mid = int(r['UiMapID'])
    if mid not in ZONE_YARDS and int(r['OrderIndex']) == 0:
        ZONE_YARDS[mid] = (abs(float(r['Region_4']) - float(r['Region_1'])), abs(float(r['Region_3']) - float(r['Region_0'])))
zone_names_lower = {v.lower(): k for k, v in ZNAME.items()}


def zone_size(area):
    mid = AREA_TO_MAP.get(area)
    return ZONE_YARDS.get(mid, (4000.0, 2700.0))


# ---------------------------------------------------------------- helpers
def qxp(qid, level):
    """Quest XP at the player's level (Classic grey-out scaling)."""
    if qid in XP:
        qlvl, xp = XP[qid]
    elif qid in WHQ and WHQ[qid].get('xp'):
        qlvl, xp = WHQ[qid].get('lv') or level, WHQ[qid]['xp']
    else:
        return 0
    diff = level - qlvl
    if diff >= 10: return int(xp * 0.1)
    if diff >= 9: return int(xp * 0.2)
    if diff >= 8: return int(xp * 0.4)
    if diff >= 7: return int(xp * 0.6)
    if diff >= 6: return int(xp * 0.8)
    return xp


def is_horde(q):
    r = q.get('races') or 0
    return r == 0 or r == 255 or (r & RACE_H) != 0


def class_ok(q):
    c = q.get('classes') or 0
    return c == 0 or (c & CLASS_BITS.get(CLASS, 0)) != 0


def npc_pos(nid):
    n = N.get(nid)
    if not n: return None
    for z, pts in (n.get('spawns') or {}).items():
        if pts:
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            return (int(z), sum(xs) / len(xs), sum(ys) / len(ys))
    if n.get('zone'):
        return (n['zone'], 50.0, 50.0)
    return None


def quest_start_pos(q):
    st = q.get('start') or {}
    for c in st.get('c', []):
        p = npc_pos(c)
        if p: return p
    return (q.get('zone'), 50.0, 50.0) if (q.get('zone') or 0) > 0 else None


def quest_end_pos(q):
    en = q.get('end') or {}
    for c in en.get('c', []):
        p = npc_pos(c)
        if p: return p
    return quest_start_pos(q)


def objective_positions(q):
    out = []
    for x in (q.get('objs') or {}).get('c', []):
        p = npc_pos(x[0])
        if p: out.append(p)
    return out


def travel(a, b, level):
    if not a or not b: return 120.0
    speed = MOUNT_SPEED if level >= MOUNT_LEVEL else RUN_SPEED
    if a[0] != b[0]:
        return ZONE_HOP
    w, h = zone_size(a[0])
    yards = math.hypot((a[1] - b[1]) / 100.0 * w, (a[2] - b[2]) / 100.0 * h)
    return yards / speed


# ---------------------------------------------------------------- dungeon packages
def dungeon_packages():
    pk = []
    for d in WQ['dungeons']:
        if d['kind'] != 'dungeon' or d.get('nodata'): continue
        own = [q for q in d['quests'] if q['side'] in (2, 3, 0)]
        if not own: continue
        pre, seen = {}, {q['id'] for q in own}

        def walk(qid):
            qq = Q.get(qid)
            preds = []
            if qq:
                preds += [(p, False) for p in qq.get('preg', [])]
                preds += [(p, len(qq.get('pre', [])) > 1) for p in qq.get('pre', [])]
                if qq.get('parent'): preds.append((qq['parent'], False))
            wq = WHQ.get(qid)
            if wq and wq.get('chain'):
                pos = next((i for i, s in enumerate(wq['chain']) if any(x[0] == qid for x in s[1])), 0)
                for s in wq['chain'][:pos]:
                    for x in s[1]: preds.append((x[0], len(s[1]) > 1))
            for p, one in preds:
                if p in seen: continue
                seen.add(p)
                pq = Q.get(p)
                if pq and not is_horde(pq): continue
                pre[p] = {'id': p, 'one': one, 'rl': max(pq.get('rl', 0) if pq else 0, WHQ.get(p, {}).get('rl', 0))}
                walk(p)
        for q in own: walk(q['id'])
        zones = DUNGEON_ZONE_ALIASES.get(d['zone'], [d['zone']])
        mobs = [n for n in N.values() if n.get('zone') in zones and n.get('lmin') and not n.get('friendly')]
        qlv = [q.get('lv') or 0 for q in own if q.get('lv')]
        mob_min = min(n['lmin'] for n in mobs) if mobs else (max(min(qlv) - 2, 1) if qlv else 0)   # new dungeons: no NPC data yet, use quest levels
        mob_max = max((n.get('lmax') or n['lmin']) for n in mobs) if mobs else (max(qlv) + 3 if qlv else 60)
        rl_of = lambda qid: max(WHQ.get(qid, {}).get('rl', 0), Q.get(qid, {}).get('rl', 0))
        # quests that require a level well above the dungeon's mobs (level-60 chains through a mid dungeon) are a later visit
        first = [q['id'] for q in own if rl_of(q['id']) <= mob_max + 2]
        later = [q['id'] for q in own if q['id'] not in first]
        later_pre = set()
        for lid in later:
            stack = [lid]
            while stack:   # prerequisites only reachable from later quests do not gate the first run
                x = stack.pop()
                for pid, pr in pre.items():
                    if pid not in later_pre and pid in (Q.get(x, {}).get('pre', []) + Q.get(x, {}).get('preg', []) + ([Q[x]['parent']] if Q.get(x, {}).get('parent') else [])):
                        later_pre.add(pid); stack.append(pid)
        first_pre = {pid: pr for pid, pr in pre.items() if pid not in later_pre}
        gate = max([rl_of(q) for q in first] + [p['rl'] for p in first_pre.values() if not p['one']] + [0])
        pk.append({'zone': d['zone'], 'n': d['n'], 'own': first, 'later': later, 'pre': first_pre, 'gate': gate, 'mobMin': mob_min, 'mobMax': mob_max,
                   'run': max(gate, mob_min + MOB_MARGIN), 'xp': sum((WHQ.get(q) or {}).get('xp') or 0 for q in first)})
    pk.sort(key=lambda p: (p['run'], p['mobMin']))
    return pk


# ---------------------------------------------------------------- RestedXP backbone
STARTS = {'durotar': '1-6 Durotar', 'tirisfal': '1-6 Tirisfal Glades', 'mulgore': '1-6 Mulgore', 'zephras': '1-14 Zephras Isle'}


def rxp_backbone(start):
    guides = {}
    for fn in glob.glob(os.path.join(RXP, 'Horde-*.lua')) + glob.glob(os.path.join(RXP, 'RestedXP-Skyborne.lua')):
        src = open(fn, encoding='utf-8').read()
        for block in re.findall(r'RegisterGuide\(\[\[(.*?)\]\]', src, re.S):
            name = re.search(r'^#name (.*)$', block, re.M)
            if not name: continue
            nxt = re.findall(r'^#next (.*)$', block, re.M)
            steps = []
            for chunk in re.split(r'^step\b.*$', block, flags=re.M)[1:]:
                st = {'goto': None, 'accept': [], 'turnin': [], 'complete': [], 'xp': None, 'text': ''}
                for line in chunk.splitlines():
                    line = line.strip()
                    m = re.match(r'\.goto (\d+),([\d.]+),([\d.]+)', line)
                    if m and not st['goto']: st['goto'] = (int(m.group(1)), float(m.group(2)), float(m.group(3)))
                    m = re.match(r'\.accept (\d+)', line)
                    if m: st['accept'].append(int(m.group(1)))
                    m = re.match(r'\.turnin (\d+)', line)
                    if m: st['turnin'].append(int(m.group(1)))
                    m = re.match(r'\.complete (\d+)', line)
                    if m: st['complete'].append(int(m.group(1)))
                    m = re.match(r'\.xp (\d+)', line)
                    if m: st['xp'] = int(m.group(1))
                    if line.startswith('>>') and not st['text']: st['text'] = re.sub(r'\|[^|]*\|[rt]?', '', line[2:]).strip()
                steps.append(st)
            guides[name.group(1).strip()] = {'next': nxt, 'steps': steps, 'file': os.path.basename(fn)}
    first = STARTS[start]
    order, cur = [], first
    while cur and cur in guides and cur not in order:
        order.append(cur)
        # take the first option that exists and is not class-gated for our class
        cur = None
        for raw in guides[order[-1]]['next']:
            cand = raw.split('<<')[0].strip().split(';')[0].strip()
            gate = raw.split('<<')[1] if '<<' in raw else ''
            if gate and ('!' + CLASS) in gate: continue
            if gate and '!' not in gate and CLASS not in gate and 'Skyborne' not in gate: continue
            if cand in guides: cur = cand; break
        if cur is None and '12-17 The Barrens' in guides and '12-17 The Barrens' not in order and order[-1] not in ('17-22 Stonetalon/Barrens/Ashenvale',):
            cur = '12-17 The Barrens'   # guides without a usable #next (Zephras Isle) continue with the Barrens
    return [(name, guides[name]) for name in order]


# ---------------------------------------------------------------- simulation
class Sim:
    def __init__(self):
        self.level, self.xp = 1, 0
        self.pos = None
        self.done, self.active = set(), set()
        self.steps = []
        self.time = 0.0

    def gain(self, amount, why):
        self.xp += amount
        while self.level < MAX_LEVEL and self.xp >= XP_TO_NEXT[self.level - 1]:
            self.xp -= XP_TO_NEXT[self.level - 1]
            self.level += 1
            self.steps.append({'t': 'level', 'lv': self.level})

    def available(self, qid):
        q = Q.get(qid)
        if not q or qid in self.done or qid in self.active: return False
        if (q.get('rl') or 0) > self.level: return False
        if q.get('preg') and not all(p in self.done for p in q['preg']): return False
        if q.get('pre') and not any(p in self.done for p in q['pre']): return False
        if q.get('parent') and q['parent'] not in self.done and q['parent'] not in self.active: return False
        if any(e in self.done for e in q.get('excl', [])): return False
        return True


def plan(start=None):
    global START
    if start: START = start
    sim = Sim()
    packages = dungeon_packages()
    prereq_deadline = {}   # quest -> earliest run level of a package needing it
    for p in packages:
        for pid in p['pre']:
            prereq_deadline[pid] = min(prereq_deadline.get(pid, 99), p['run'])
    # --- backbone
    for name, g in rxp_backbone(START):
        sim.steps.append({'t': 'guide', 'n': name, 'src': 'RestedXP ' + g['file']})
        for st in g['steps']:
            if st['goto']: sim.pos = (None, st['goto'][1], st['goto'][2], st['goto'][0])
            for qid in st['accept']:
                sim.active.add(qid)
                sim.steps.append({'t': 'accept', 'q': qid, 'lv': sim.level, 'rxp': 1})
            for qid in st['turnin']:
                sim.active.discard(qid); sim.done.add(qid)
                xp = qxp(qid, sim.level)
                sim.steps.append({'t': 'turnin', 'q': qid, 'lv': sim.level, 'xp': xp, 'rxp': 1})
                sim.gain(xp + int(xp * KILL_XP_FRACTION), 'quest')
                run_dungeons(sim, packages, prereq_deadline)
            if st['xp'] and sim.level < st['xp']:
                sim.steps.append({'t': 'grind', 'to': st['xp'], 'lv': sim.level})
                need = 0
                while sim.level < st['xp']:
                    need += XP_TO_NEXT[sim.level - 1] - sim.xp
                    sim.gain(XP_TO_NEXT[sim.level - 1] - sim.xp, 'grind')
            run_dungeons(sim, packages, prereq_deadline)
    sim.steps.append({'t': 'guide', 'n': 'Generated %d-60' % sim.level, 'src': 'planner'})
    # position after backbone: use the zone of the last turned-in quest
    last = next((s['q'] for s in reversed(sim.steps) if s.get('t') == 'turnin'), None)
    sim.pos = quest_end_pos(Q[last]) if last in Q else None
    # --- generated route
    pool = [qid for qid, q in Q.items() if is_horde(q) and class_ok(q) and (q.get('zone') or 0) > 0 and not (q.get('special', 0) & 1)
            and q['zone'] not in {p['zone'] for p in packages} and not q.get('maxlv')]
    stall = 0
    while sim.level < MAX_LEVEL and stall < 3:
        run_dungeons(sim, packages, prereq_deadline)
        best, best_score = None, 0
        for qid in pool:
            if not sim.available(qid): continue
            q = Q[qid]
            xp = qxp(qid, sim.level)
            if xp <= 0: continue
            sp, ep = quest_start_pos(q), quest_end_pos(q)
            cost = travel(sim.pos, sp, sim.level) + travel(sp, ep, sim.level) + 60.0
            objs = q.get('objs') or {}
            for k, lst in objs.items():
                cost += OBJECTIVE_TIME.get(k, 120.0) * (len(lst) if isinstance(lst, list) else 1)
            for op in objective_positions(q)[:3]:
                cost += travel(sp, op, sim.level) * 0.5
            score = (xp * (1 + KILL_XP_FRACTION)) / cost
            dl = prereq_deadline.get(qid)
            if dl is not None:
                score *= 3.0 if sim.level >= dl - 1 else 1.6
            # prefer quests near the player's level band and in the current zone
            if sp and sim.pos and sp[0] == sim.pos[0]: score *= 1.5
            if (q.get('lv') or 0) > sim.level + 3: score *= 0.5
            if score > best_score: best, best_score = qid, score
        if not best:
            stall += 1
            sim.steps.append({'t': 'grind', 'to': sim.level + 1, 'lv': sim.level})
            sim.gain(XP_TO_NEXT[sim.level - 1] - sim.xp, 'grind')
            continue
        stall = 0
        q = Q[best]
        sp, ep = quest_start_pos(q), quest_end_pos(q)
        sim.steps.append({'t': 'accept', 'q': best, 'lv': sim.level, 'pos': sp})
        sim.active.add(best)
        xp = qxp(best, sim.level)
        sim.active.discard(best); sim.done.add(best)
        sim.steps.append({'t': 'turnin', 'q': best, 'lv': sim.level, 'xp': xp, 'pos': ep})
        sim.gain(xp + int(xp * KILL_XP_FRACTION), 'quest')
        sim.pos = ep
    run_dungeons(sim, packages, prereq_deadline)   # anything gated at the cap
    return sim, packages


def force_quest(sim, qid, why, depth=0):
    """Do a quest now, doing its own prerequisites first (depth-first). Returns False when it cannot be done yet."""
    if qid in sim.done: return True
    q = Q.get(qid)
    if not q or depth > 12: return False
    if (q.get('rl') or 0) > sim.level: return False
    for p in q.get('preg', []):
        if not force_quest(sim, p, why, depth + 1): return False
    if q.get('pre') and not any(p in sim.done for p in q['pre']):
        if not any(force_quest(sim, p, why, depth + 1) for p in sorted(q['pre'], key=lambda x: Q.get(x, {}).get('rl', 0))): return False
    if q.get('parent') and q['parent'] not in sim.done and not force_quest(sim, q['parent'], why, depth + 1): return False
    xp = qxp(qid, sim.level)
    sim.active.discard(qid); sim.done.add(qid)
    sim.steps.append({'t': 'accept', 'q': qid, 'lv': sim.level, 'forced': why, 'pos': quest_start_pos(q)})
    sim.steps.append({'t': 'turnin', 'q': qid, 'lv': sim.level, 'xp': xp, 'forced': why, 'pos': quest_end_pos(q)})
    sim.gain(xp + int(xp * KILL_XP_FRACTION), 'prereq')
    sim.pos = quest_end_pos(q)
    return True


def run_dungeons(sim, packages, prereq_deadline):
    for p in packages:
        if p.get('done') or sim.level < p['run']: continue
        missing = [pid for pid, pr in p['pre'].items() if pid not in sim.done and not pr['one']]
        for pid in sorted(missing, key=lambda x: p['pre'][x]['rl']):   # pull forward, chains first
            if not force_quest(sim, pid, p['n']):
                sim.steps.append({'t': 'note', 'msg': 'prerequisite %d (%s) for %s not schedulable at level %d (req %s)' % (pid, Q.get(pid, {}).get('n', '?'), p['n'], sim.level, p['pre'][pid]['rl'])})
        held = [qid for qid in p['own'] if qid in sim.active or qid in sim.done]
        for qid in p['own']:
            if qid not in sim.active and qid not in sim.done:
                sim.active.add(qid)
                sim.steps.append({'t': 'accept', 'q': qid, 'lv': sim.level, 'dungeon': p['n']})
        sim.steps.append({'t': 'dungeon', 'zone': p['zone'], 'n': p['n'], 'lv': sim.level, 'run': p['run'], 'gate': p['gate'], 'mobMin': p['mobMin'], 'quests': p['own']})
        total = 0
        for qid in p['own']:
            xp = qxp(qid, sim.level)
            total += xp
            sim.active.discard(qid); sim.done.add(qid)
            sim.steps.append({'t': 'turnin', 'q': qid, 'lv': sim.level, 'xp': xp, 'dungeon': p['n']})
        sim.gain(total + int(total * KILL_XP_FRACTION * 1.5), 'dungeon')
        p['done'] = True
        p['at'] = sim.level


def annotate(sim):
    for s in sim.steps:
        if s.get('q'):
            qid = s['q']
            s['n'] = Q[qid]['n'] if qid in Q else (WHQ.get(qid, {}).get('n') or '#%d' % qid)
            if qid in Q:
                p = quest_start_pos(Q[qid]) if s['t'] == 'accept' else quest_end_pos(Q[qid])
                if p and p[0] and p[0] > 0:
                    s['zone'] = p[0]
                    if 'pos' not in s: s['pos'] = p
                elif (Q[qid].get('zone') or 0) > 0: s['zone'] = Q[qid]['zone']
            elif s.get('pos') and len(s['pos']) == 4 and s['pos'][3]:   # RestedXP goto: uiMapID known, area unknown
                area = next((a for a, m in AREA_TO_MAP.items() if m == s['pos'][3]), None)
                if area: s['zone'] = area; s['pos'] = (area, s['pos'][1], s['pos'][2])


ALL = {}
for st_ in (STARTS if '--all' in ARG or '--start' not in ARG else [START]):
    sim_, packages_ = plan(st_)
    annotate(sim_)
    ALL[st_] = (sim_, packages_)
START = ARG[ARG.index('--start') + 1] if '--start' in ARG else 'durotar'
sim, packages = ALL[START]
out = {'start': START, 'cls': CLASS, 'mobMargin': MOB_MARGIN, 'finalLevel': sim.level,
       'dungeons': [{'zone': p['zone'], 'n': p['n'], 'run': p['run'], 'gate': p['gate'], 'mobMin': p['mobMin'], 'mobMax': p['mobMax'], 'at': p.get('at'), 'pre': sorted(p['pre']), 'own': p['own'], 'later': p['later'], 'xp': p['xp']} for p in packages],
       'steps': sim.steps}
with open(os.path.join(OUT, 'route.js'), 'w', encoding='utf-8') as f:
    f.write('window.FR_ROUTE=' + json.dumps(out, separators=(',', ':'), ensure_ascii=False) + ';\n')
# ---------------------------------------------------------------- addon export (AlcRoute reads RouteData.lua)
ADDON_DIR = r'D:\addons\wow-addons\AlcRoute'
if os.path.isdir(ADDON_DIR):
    def lstr(s):
        return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'
    lines = ['-- GENERATED by forever-ref/route.py; do not edit. Class %s.' % CLASS, 'AlcRouteData = {', '  meta = { cls = %s, starts = { %s } },' % (lstr(CLASS), ', '.join(lstr(k) for k in ALL)), '  dungeons = {']
    for p in packages:
        lines.append('    { zone = %d, n = %s, run = %d, quests = { %s }, pre = { %s } },' % (p['zone'], lstr(p['n']), p['run'], ', '.join(str(q) for q in p['own']), ', '.join(str(q) for q in sorted(p['pre']))))
    lines.append('  },')
    # quests that must not be auto-skipped in game: dungeon packages, their prerequisites, and anything those depend on
    required = set()
    for p in packages:
        required.update(p['own']); required.update(p['pre']); required.update(p['later'])
    frontier = list(required)
    while frontier:
        q = Q.get(frontier.pop()) or {}
        for dep in q.get('pre', []) + q.get('preg', []) + ([q['parent']] if q.get('parent') else []):
            if dep not in required:
                required.add(dep); frontier.append(dep)
    lines.append('  routes = {')
    for st_, (sim_, _) in ALL.items():
        lines.append('    [%s] = {' % lstr(st_))
        for s in sim_.steps:
            t = s['t']
            if t in ('guide', 'note'):
                continue
            parts = ['t = %s' % lstr(t), 'lv = %d' % (s.get('lv') or 0)]
            if s.get('q'):
                parts.append('q = %d' % s['q']); parts.append('n = %s' % lstr(s.get('n', '')))
                ql = (Q.get(s['q']) or {}).get('lv') or (WHQ.get(s['q']) or {}).get('lv') or XP.get(s['q'], (0, 0))[0]
                if ql: parts.append('ql = %d' % ql)
                if s['q'] in required: parts.append('req = 1')
            if t == 'dungeon':
                parts.append('zone = %d' % s['zone']); parts.append('n = %s' % lstr(s['n'])); parts.append('quests = { %s }' % ', '.join(str(q) for q in s['quests']))
            if t == 'grind':
                parts.append('to = %d' % s['to'])
            pos = s.get('pos')
            if pos and pos[0] and pos[0] > 0 and AREA_TO_MAP.get(pos[0]) and pos[1] is not None:
                parts.append('m = %d' % AREA_TO_MAP[pos[0]]); parts.append('x = %.1f' % pos[1]); parts.append('y = %.1f' % pos[2]); parts.append('z = %s' % lstr(ZNAME.get(pos[0], ''))); parts.append('zid = %d' % pos[0])
            elif s.get('zone'):
                parts.append('z = %s' % lstr(ZNAME.get(s['zone'], ''))); parts.append('zid = %d' % s['zone'])
            if s.get('dungeon'): parts.append('d = %s' % lstr(s['dungeon']))
            if s.get('forced'): parts.append('f = %s' % lstr(s['forced']))
            lines.append('      { %s },' % ', '.join(parts))
        lines.append('    },')
    lines.append('  },')
    lines.append('}')
    with open(os.path.join(ADDON_DIR, 'RouteData.lua'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('wrote', os.path.join(ADDON_DIR, 'RouteData.lua'))

print('Route: start %s, class %s, reaches level %d in %d steps (%d quests turned in)' % (START, CLASS, sim.level, len(sim.steps), sum(1 for s in sim.steps if s['t'] == 'turnin')))
print('Dungeon schedule:')
for p in packages:
    print('  %-24s run at %2s  (gate %2d, mobs %2d-%2d, %d quests%s, %d prereqs)' % (p['n'], p.get('at', '--'), p['gate'], p['mobMin'], p['mobMax'], len(p['own']), (' +%d later' % len(p['later'])) if p['later'] else '', len(p['pre'])))
lv_steps = [(s['lv'], i) for i, s in enumerate(sim.steps) if s['t'] == 'level']
zones_seq = []
for s in sim.steps:
    z = s.get('zone')
    if z and (not zones_seq or zones_seq[-1][0] != z): zones_seq.append((z, s.get('lv')))
print('Zone sequence:', ' > '.join('%s@%s' % (ZNAME.get(z, z), lv) for z, lv in zones_seq[:40]))
print('Grinds:', sum(1 for s in sim.steps if s['t'] == 'grind'), '| forced prereqs:', sum(1 for s in sim.steps if s['t'] == 'turnin' and s.get('forced')))
notes = [s['msg'] for s in sim.steps if s['t'] == 'note']
if notes: print('Notes:\n  ' + '\n  '.join(notes[:15]))
