#!/usr/bin/env python3
"""forever-ref build: wago.tools DB2 CSVs for the WoW Forever build -> static site data.

Usage:  python build.py                    build the pinned DEFAULT_BUILD (cached CSVs in cache/<build>/)
        python build.py --latest           pick the newest Forever build listed by wago.tools
        python build.py --build 1.60.1.X   build a specific build
        python build.py --snapshot-only    only write builds/<build>.json.gz (for seeding patch history)
        python build.py --refresh          re-download every table

Every run writes a snapshot of the comparable data to builds/<build>.json.gz; consecutive snapshots
are diffed into site/data/patches.js (the "Patches" page).
"""
import csv, json, os, re, sys, math, gzip, datetime, urllib.request, collections

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_BUILD = '1.60.1.69913'  # WoW Forever (wago.tools product wow_classic_beta)
ERA_BUILD = '1.15.9.69722'      # Classic Era, used only for the "what changed" diff
PRODUCT = 'wow_classic_beta'
CACHE = os.path.join(ROOT, 'cache')
SITE = os.path.join(ROOT, 'site')
DATA = os.path.join(SITE, 'data')
BUILDS = os.path.join(ROOT, 'builds')
REFRESH = '--refresh' in sys.argv
SNAPSHOT_ONLY = '--snapshot-only' in sys.argv
UA = {'User-Agent': 'Mozilla/5.0 forever-ref/1.0'}


def vtuple(v):
    return tuple(int(x) for x in v.split('.'))


def latest_build():
    data = json.loads(urllib.request.urlopen(urllib.request.Request('https://wago.tools/api/builds', headers=UA), timeout=60).read())
    forever = [b['version'] for b in data.get(PRODUCT, []) if b['version'].startswith('1.') and vtuple(b['version']) >= (1, 60)]
    if not forever:
        raise SystemExit('no Forever build found on wago.tools')
    return max(forever, key=vtuple)


BUILD = DEFAULT_BUILD
if '--build' in sys.argv:
    BUILD = sys.argv[sys.argv.index('--build') + 1]
elif '--latest' in sys.argv:
    BUILD = latest_build()
    print('Latest Forever build on wago.tools:', BUILD)
ERA_CACHE = os.path.join(CACHE, ERA_BUILD)

os.makedirs(os.path.join(CACHE, BUILD), exist_ok=True)
os.makedirs(ERA_CACHE, exist_ok=True)
os.makedirs(DATA, exist_ok=True)
os.makedirs(BUILDS, exist_ok=True)


def fetch(table, build=None, folder=None, need=()):
    build = build or BUILD
    folder = folder or os.path.join(CACHE, build)
    path = os.path.join(folder, table + '.csv')
    if REFRESH or not os.path.exists(path) or os.path.getsize(path) == 0:
        url = f'https://wago.tools/db2/{table}/csv?build={build}'
        print('  download', table, build)
        data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180).read()
        if data.startswith(b'{"errors"') or data.startswith(b'{"message"'):
            raise SystemExit(f'{table} not available for build {build}: {data[:120]!r}')
        with open(path, 'wb') as f:
            f.write(data)
    with open(path, encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    if rows:
        missing = [c for c in need if c not in rows[0]]
        if missing:
            raise SystemExit(f'{table} ({build}) is missing expected columns {missing}; layout changed, update build.py')
    return rows


def I(s):
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return 0


def Fl(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def by_id(rows, col='ID'):
    return {I(r[col]): r for r in rows}


def group(rows, col):
    g = collections.defaultdict(list)
    for r in rows:
        g[I(r[col])].append(r)
    return g


print('Loading tables for', BUILD)
T = {}
T['ItemSparse'] = fetch('ItemSparse', need=('Display_lang', 'ItemLevel', 'OverallQualityID', 'StatModifier_bonusStat_0', 'StatPercentEditor_0', 'DmgVariance', 'ItemDelay'))
T['Item'] = fetch('Item', need=('ClassID', 'SubclassID', 'InventoryType', 'IconFileDataID'))
T['ItemClass'] = fetch('ItemClass', need=('ClassID', 'ClassName_lang'))
T['ItemSubClass'] = fetch('ItemSubClass', need=('ClassID', 'SubClassID', 'DisplayName_lang'))
T['ItemEffect'] = fetch('ItemEffect', need=('TriggerType', 'SpellID', 'CoolDownMSec'))
T['ItemXItemEffect'] = fetch('ItemXItemEffect', need=('ItemEffectID', 'ItemID'))
T['ItemSet'] = fetch('ItemSet', need=('Name_lang', 'ItemID_0'))
T['ItemSetSpell'] = fetch('ItemSetSpell', need=('SpellID', 'Threshold', 'ItemSetID'))
T['RandPropPoints'] = fetch('RandPropPoints', need=('EpicF_0', 'SuperiorF_0', 'GoodF_0'))
for t in ('ItemDamageOneHand', 'ItemDamageTwoHand', 'ItemDamageOneHandCaster', 'ItemDamageTwoHandCaster',
          'ItemDamageRanged', 'ItemDamageThrown', 'ItemDamageWand', 'ItemDamageAmmo', 'ItemArmorShield'):
    T[t] = fetch(t, need=('ItemLevel', 'Quality_0'))
T['ItemArmorTotal'] = fetch('ItemArmorTotal', need=('ItemLevel', 'Cloth', 'Plate'))
T['ItemArmorQuality'] = fetch('ItemArmorQuality', need=('Qualitymod_0',))
T['ArmorLocation'] = fetch('ArmorLocation', need=('Clothmodifier', 'Platemodifier'))
T['SpellName'] = fetch('SpellName', need=('Name_lang',))
T['Spell'] = fetch('Spell', need=('Description_lang', 'AuraDescription_lang', 'NameSubtext_lang'))
T['SpellMisc'] = fetch('SpellMisc', need=('SpellID', 'DurationIndex', 'CastingTimeIndex', 'RangeIndex', 'SpellIconFileDataID'))
T['SpellEffect'] = fetch('SpellEffect', need=('SpellID', 'Effect', 'EffectIndex', 'EffectBasePointsF', 'EffectItemType', 'EffectAura', 'EffectAuraPeriod', 'EffectMiscValue_0', 'EffectTriggerSpell'))
T['SpellReagents'] = fetch('SpellReagents', need=('SpellID', 'Reagent_0', 'ReagentCount_0'))
T['SpellDuration'] = fetch('SpellDuration', need=('Duration',))
T['SpellCastTimes'] = fetch('SpellCastTimes', need=('Base',))
T['SpellRange'] = fetch('SpellRange', need=('RangeMax_0',))
T['SpellRadius'] = fetch('SpellRadius', need=('Radius',))
T['SpellLevels'] = fetch('SpellLevels', need=('SpellID', 'BaseLevel', 'SpellLevel'))
T['SpellPower'] = fetch('SpellPower', need=('SpellID', 'ManaCost', 'PowerType', 'PowerCostPct'))
T['SpellCooldowns'] = fetch('SpellCooldowns', need=('SpellID', 'RecoveryTime', 'CategoryRecoveryTime'))
T['SpellAuraOptions'] = fetch('SpellAuraOptions', need=('SpellID', 'ProcChance', 'ProcCharges', 'CumulativeAura'))
T['SpellTargetRestrictions'] = fetch('SpellTargetRestrictions', need=('SpellID', 'MaxTargets'))
T['SpellItemEnchantment'] = fetch('SpellItemEnchantment', need=('Name_lang',))
T['SkillLine'] = fetch('SkillLine', need=('DisplayName_lang', 'CategoryID', 'ParentSkillLineID', 'SpellIconFileID'))
T['SkillLineAbility'] = fetch('SkillLineAbility', need=('SkillLine', 'Spell', 'MinSkillLineRank', 'TrivialSkillLineRankHigh', 'TrivialSkillLineRankLow', 'AcquireMethod', 'TradeSkillCategoryID', 'ClassMask', 'SupercedesSpell'))
T['TradeSkillCategory'] = fetch('TradeSkillCategory', need=('Name_lang', 'ParentTradeSkillCategoryID', 'OrderIndex'))
T['ChrClasses'] = fetch('ChrClasses', need=('Name_lang', 'ID'))
T['AreaTable'] = fetch('AreaTable', need=('AreaName_lang', 'ContinentID', 'ParentAreaID', 'ExplorationLevel'))
T['Map'] = fetch('Map', need=('MapName_lang', 'InstanceType'))
T['ManifestInterfaceData'] = fetch('ManifestInterfaceData', need=('FilePath', 'FileName'))
T['ItemLimitCategory'] = fetch('ItemLimitCategory', need=('Name_lang', 'Quantity'))
T['Faction'] = fetch('Faction', need=('Name_lang',))

print('Loading Classic Era tables for diff', ERA_BUILD)
E = {}
E['ItemSparse'] = fetch('ItemSparse', ERA_BUILD, ERA_CACHE, need=('Display_lang', 'ItemLevel'))
E['Item'] = fetch('Item', ERA_BUILD, ERA_CACHE, need=('ClassID', 'SubclassID'))
E['SpellName'] = fetch('SpellName', ERA_BUILD, ERA_CACHE, need=('Name_lang',))
E['SkillLineAbility'] = fetch('SkillLineAbility', ERA_BUILD, ERA_CACHE, need=('SkillLine', 'Spell', 'MinSkillLineRank'))
E['SpellReagents'] = fetch('SpellReagents', ERA_BUILD, ERA_CACHE, need=('SpellID', 'Reagent_0'))
E['SpellEffect'] = fetch('SpellEffect', ERA_BUILD, ERA_CACHE, need=('SpellID', 'Effect', 'EffectItemType'))

# ---------------------------------------------------------------- lookups
ICON = {}
for r in T['ManifestInterfaceData']:
    if r['FilePath'].lower().startswith('interface\\icons'):
        ICON[I(r['ID'])] = re.sub(r'\.blp$', '', r['FileName'], flags=re.I).lower()


def icon(fdid):
    return ICON.get(I(fdid), '')


SPARSE = by_id(T['ItemSparse'])
ITEM = by_id(T['Item'])
SPELLNAME = {I(r['ID']): r['Name_lang'] for r in T['SpellName']}
SPELL = by_id(T['Spell'])
MISC = {}
for r in T['SpellMisc']:
    MISC.setdefault(I(r['SpellID']), r)
EFFECTS = group(T['SpellEffect'], 'SpellID')
for k in EFFECTS:
    EFFECTS[k].sort(key=lambda r: I(r['EffectIndex']))
REAGENTS = {}
for r in T['SpellReagents']:
    REAGENTS.setdefault(I(r['SpellID']), r)
DURATION = by_id(T['SpellDuration'])
CASTTIME = by_id(T['SpellCastTimes'])
RANGE = by_id(T['SpellRange'])
RADIUS = by_id(T['SpellRadius'])
LEVELS = {}
for r in T['SpellLevels']:
    if I(r['DifficultyID']) == 0 or I(r['SpellID']) not in LEVELS:
        LEVELS[I(r['SpellID'])] = r
POWER = group(T['SpellPower'], 'SpellID')
COOLDOWN = {}
for r in T['SpellCooldowns']:
    if I(r['DifficultyID']) == 0 or I(r['SpellID']) not in COOLDOWN:
        COOLDOWN[I(r['SpellID'])] = r
AURAOPT = {}
for r in T['SpellAuraOptions']:
    AURAOPT.setdefault(I(r['SpellID']), r)
TARGETS = {}
for r in T['SpellTargetRestrictions']:
    TARGETS.setdefault(I(r['SpellID']), r)
ENCHANT = by_id(T['SpellItemEnchantment'])
SKILLLINE = by_id(T['SkillLine'])
SLA = T['SkillLineAbility']
TSC = by_id(T['TradeSkillCategory'])
CLASSES = {I(r['ID']): r['Name_lang'] for r in T['ChrClasses']}
ITEMCLASS = {I(r['ClassID']): r['ClassName_lang'] for r in T['ItemClass']}
LIMITCAT = by_id(T['ItemLimitCategory'])
FACTION = by_id(T['Faction'])
ITEMSUB = {(I(r['ClassID']), I(r['SubClassID'])): (r['DisplayName_lang'] or r['VerboseName_lang']) for r in T['ItemSubClass']}

# item -> effects
ITEMFX = collections.defaultdict(list)
_fx = by_id(T['ItemEffect'])
for r in T['ItemXItemEffect']:
    fx = _fx.get(I(r['ItemEffectID']))
    if fx:
        ITEMFX[I(r['ItemID'])].append(fx)

# ---------------------------------------------------------------- spell text
def fmt_num(v):
    if v is None:
        return '?'
    if abs(v - round(v)) < 1e-6:
        return str(int(round(v)))
    return ('%.1f' % v).rstrip('0').rstrip('.')


def fmt_dur(ms):
    if ms is None:
        return '?'
    if ms < 0:
        return 'until cancelled'
    s = ms / 1000.0
    if s < 60:
        return fmt_num(s) + ' sec'
    m = s / 60.0
    if m < 60:
        return fmt_num(m) + ' min'
    h = m / 60.0
    if h < 24:
        return fmt_num(h) + (' hr' if h == 1 else ' hrs')
    d = h / 24.0
    return fmt_num(d) + (' day' if d == 1 else ' days')


def spell_duration_ms(sid):
    m = MISC.get(sid)
    if not m:
        return None
    d = DURATION.get(I(m['DurationIndex']))
    return I(d['Duration']) if d else None


PERIODIC_AURAS = {3, 8, 20, 21, 23, 24, 53, 64, 89}


def spell_vars(sid):
    """Per-spell variables used by tooltip tokens."""
    v = {}
    effs = EFFECTS.get(sid, [])
    dur = spell_duration_ms(sid)
    v['d'] = dur
    for e in effs:
        idx = I(e['EffectIndex']) + 1
        s = Fl(e['EffectBasePointsF'])
        var = Fl(e.get('Variance', 0))
        aura = I(e['EffectAura'])
        period = I(e['EffectAuraPeriod'])
        if period <= 0:
            period = 5000 if aura in (84, 85) else (1000 if aura in PERIODIC_AURAS else 0)
        ticks = (dur / period) if (dur and dur > 0 and period > 0) else 1
        v['s%d' % idx] = abs(s)
        v['w%d' % idx] = abs(s)
        v['m%d' % idx] = abs(s * (1 - var / 2))
        v['M%d' % idx] = abs(s * (1 + var / 2))
        v['o%d' % idx] = float(round(abs(s * ticks)))
        v['t%d' % idx] = period / 1000.0 if period else 0
        rad = RADIUS.get(I(e['EffectRadiusIndex_0']))
        v['a%d' % idx] = Fl(rad['Radius']) if rad else 0
        v['A%d' % idx] = v['a%d' % idx]
        v['x%d' % idx] = I(e['EffectChainTargets'])
        v['q%d' % idx] = I(e['EffectMiscValue_0'])
        v['b%d' % idx] = Fl(e['EffectPointsPerResource'])
        v['e%d' % idx] = Fl(e['EffectAmplitude'])
    ao = AURAOPT.get(sid)
    v['h'] = I(ao['ProcChance']) if ao else 0
    v['n'] = I(ao['ProcCharges']) if ao else 0
    v['u'] = I(ao['CumulativeAura']) if ao else 0
    tr = TARGETS.get(sid)
    v['i'] = I(tr['MaxTargets']) if tr else 0
    m = MISC.get(sid)
    rg = RANGE.get(I(m['RangeIndex'])) if m else None
    v['r'] = Fl(rg['RangeMax_0']) if rg else 0
    v['R'] = v['r']
    return v


_VARS_CACHE = {}


def get_vars(sid):
    if sid not in _VARS_CACHE:
        _VARS_CACHE[sid] = spell_vars(sid)
    return _VARS_CACHE[sid]


TOKEN_RE = re.compile(r'\$(\d*)([smMowtaAxqbe])(\d+)|\$(\d*)([dhnuirR])(?![a-zA-Z])')
OPS_RE = re.compile(r'\$([/*+-])(\d+(?:\.\d+)?);(\d*)([smMowtaAxqbe])(\d+)')
EXPR_RE = re.compile(r'\$\{([^{}]*)\}(\.\d)?')
COND_RE = re.compile(r'\$\?[^\[\]$]*\[([^\[\]]*)\](?:\[([^\[\]]*)\])?')


def tok_value(sid, letter, idx):
    v = get_vars(sid)
    key = letter + (idx or '')
    if letter == 'd':
        return v.get('d')
    return v.get(key)


def render_desc(sid, text, depth=0):
    if not text:
        return ''
    if depth > 2:
        return ''
    # cross-spell references
    text = re.sub(r'\$@spellname(\d+)', lambda m: SPELLNAME.get(I(m.group(1)), ''), text)
    text = re.sub(r'\$@spellicon(\d+)', '', text)

    def sub_desc(m):
        o = I(m.group(1))
        s = SPELL.get(o)
        return render_desc(o, s['Description_lang'], depth + 1) if s else ''

    def sub_aura(m):
        o = I(m.group(1))
        s = SPELL.get(o)
        return render_desc(o, s['AuraDescription_lang'], depth + 1) if s else ''
    text = re.sub(r'\$@spelldesc(\d+)', sub_desc, text)
    text = re.sub(r'\$@spellaura(\d+)', sub_aura, text)
    text = re.sub(r'\$@spelltooltip(\d+)', sub_desc, text)
    # conditionals: keep the first branch
    for _ in range(6):
        new = COND_RE.sub(lambda m: m.group(1), text)
        if new == text:
            break
        text = new

    # arithmetic prefix ops  $/10;s1
    def sub_ops(m):
        op, num, osid, letter, idx = m.groups()
        val = tok_value(I(osid) if osid else sid, letter, idx)
        if val is None:
            return '?'
        n = float(num)
        if op == '/':
            val = val / n if n else val
        elif op == '*':
            val = val * n
        elif op == '+':
            val = val + n
        else:
            val = val - n
        return fmt_num(val)
    text = OPS_RE.sub(sub_ops, text)

    # plain tokens
    def sub_tok(m):
        if m.group(2):
            osid, letter, idx = m.group(1), m.group(2), m.group(3)
        else:
            osid, letter, idx = m.group(4), m.group(5), None
        val = tok_value(I(osid) if osid else sid, letter, idx)
        if letter == 'd':
            return fmt_dur(val)
        if val is None:
            return '?'
        return fmt_num(val)
    text = TOKEN_RE.sub(sub_tok, text)

    # ${expr}
    def sub_expr(m):
        expr, dec = m.group(1), m.group(2)
        e = expr.replace('$', '')
        if re.fullmatch(r'[\d\.\s()+\-*/]+', e):
            try:
                val = eval(e, {'__builtins__': {}}, {})
                if dec:
                    return ('%.' + dec[1] + 'f') % val
                return fmt_num(val)
            except Exception:
                pass
        return '?'   # expression depends on values the client computes at runtime (spell power, level)
    text = EXPR_RE.sub(sub_expr, text)

    # plurals $lsingular:plural;  and |4sing:plur;
    def sub_plural(m):
        prefix = text[:m.start()]
        nums = re.findall(r'(\d+(?:\.\d+)?)', prefix)
        n = float(nums[-1]) if nums else 2
        return m.group(1) if n == 1 else m.group(2)
    text = re.sub(r'\$[lL]([^:;$]*):([^;$]*);', sub_plural, text)
    text = re.sub(r'\|4([^:;]*):([^;]*);', sub_plural, text)
    text = re.sub(r'\$[gG]([^:;$]*):([^;$]*);', lambda m: m.group(1), text)
    text = re.sub(r'\|c[0-9a-fA-F]{8}', '', text).replace('|r', '')
    text = text.replace('|n', '\n')
    text = re.sub(r'\$<[^>]*>', '?', text)
    text = text.replace('$PL', 'level')
    return text.strip()


# ---------------------------------------------------------------- item math
SLOT_INDEX = {1: 0, 4: 0, 5: 0, 7: 0, 17: 0, 20: 0,
              3: 1, 6: 1, 8: 1, 10: 1, 12: 1,
              2: 2, 9: 2, 11: 2, 14: 2, 16: 2, 23: 2,
              13: 3, 21: 3, 22: 3,
              15: 4, 25: 4, 26: 4}
TWO_HAND_SUB = {1, 5, 6, 8, 10, 20}
RANGED_SUB = {2, 3, 18}


DMG_TABLES = ('ItemDamageOneHand', 'ItemDamageTwoHand', 'ItemDamageOneHandCaster', 'ItemDamageTwoHandCaster',
              'ItemDamageRanged', 'ItemDamageThrown', 'ItemDamageWand', 'ItemDamageAmmo', 'ItemArmorShield')


class ItemMath:
    """Item stat / armor / damage math (TrinityCore formulas) over one build's tables."""

    def __init__(self, load):
        self.RPP = by_id(load('RandPropPoints'))
        self.DMG = {t: {I(r['ItemLevel']): r for r in load(t)} for t in DMG_TABLES}
        self.ARMOR_TOTAL = {I(r['ItemLevel']): r for r in load('ItemArmorTotal')}
        self.ARMOR_QUAL = by_id(load('ItemArmorQuality'))
        self.ARMOR_LOC = by_id(load('ArmorLocation'))
        sample = next(iter(self.RPP.values()))
        self.rpp_cols = {4: 'EpicF', 3: 'SuperiorF', 2: 'GoodF'} if 'EpicF_0' in sample else {4: 'Epic', 3: 'Superior', 2: 'Good'}

    def rand_prop_points(self, ilvl, quality, invtype):
        slot = SLOT_INDEX.get(invtype)
        row = self.RPP.get(ilvl)
        if slot is None or row is None:
            return 0.0
        col = self.rpp_cols[4 if quality >= 4 else (3 if quality == 3 else 2)]
        return Fl(row['%s_%d' % (col, slot)])

    def stats(self, sp, quality, invtype):
        if 'StatModifier_bonusAmount_0' in sp:   # Classic Era layout: values stored directly
            out = []
            for i in range(10):
                st, v = I(sp['StatModifier_bonusStat_%d' % i]), I(sp['StatModifier_bonusAmount_%d' % i])
                if st >= 0 and v:
                    out.append([st, v])
            return out
        pts = self.rand_prop_points(I(sp['ItemLevel']), quality, invtype)
        out = []
        for i in range(10):
            st = I(sp['StatModifier_bonusStat_%d' % i])
            if st < 0:
                continue
            pct = I(sp['StatPercentEditor_%d' % i])
            val = int(math.floor(pts * pct / 10000.0 + 0.5))
            if val:
                out.append([st, val])
        return out

    def armor(self, cls, sub, inv, ilvl, quality, it=None):
        if it is not None and 'Resistances_0' in it:   # Classic Era layout: armor stored on the item
            return I(it['Resistances_0'])
        if cls != 4 or quality > 6:
            return 0
        q = min(quality, 6)
        if sub == 6:  # shield
            row = self.DMG['ItemArmorShield'].get(ilvl)
            return int(Fl(row['Quality_%d' % q]) + 0.5) if row else 0
        if sub < 1 or sub > 4:
            return 0
        if inv == 20:
            inv = 5
        total, aq, loc = self.ARMOR_TOTAL.get(ilvl), self.ARMOR_QUAL.get(ilvl), self.ARMOR_LOC.get(inv)
        if not (total and aq and loc):
            return 0
        tcol, lcol = {1: ('Cloth', 'Clothmodifier'), 2: ('Leather', 'Leathermodifier'),
                      3: ('Mail', 'Chainmodifier'), 4: ('Plate', 'Platemodifier')}[sub]
        return int(math.floor(Fl(aq['Qualitymod_%d' % q]) * Fl(total[tcol]) * Fl(loc[lcol]) + 0.5))

    def damage(self, cls, sub, sp, quality, it=None):
        if it is not None and 'MinDamage_0' in it:   # Classic Era layout: damage stored on the item
            lo, hi, delay = I(it['MinDamage_0']), I(it['MaxDamage_0']), I(sp['ItemDelay'])
            if not (lo or hi) or delay <= 0:
                return None
            speed = delay / 1000.0
            return {'min': lo, 'max': hi, 'speed': speed, 'dps': round((lo + hi) / 2.0 / speed, 2)}
        ilvl = I(sp['ItemLevel'])
        q = 3 if quality == 7 else min(quality, 6)
        if cls == 6:
            row = self.DMG['ItemDamageAmmo'].get(ilvl)
            return {'dps': round(Fl(row['Quality_%d' % q]), 1)} if row else None
        if cls != 2:
            return None
        caster = bool(I(sp.get('Flags_1', 0)) & 0x200)
        if sub in TWO_HAND_SUB or sub in RANGED_SUB:   # Forever: bows/guns/crossbows use the two-hand table (verified vs Wowhead)
            t = 'ItemDamageTwoHandCaster' if caster else 'ItemDamageTwoHand'
        elif sub == 16:
            t = 'ItemDamageThrown'
        elif sub == 19:
            t = 'ItemDamageWand'
        else:
            t = 'ItemDamageOneHandCaster' if caster else 'ItemDamageOneHand'
        row = self.DMG[t].get(ilvl)
        delay = I(sp['ItemDelay'])
        if not row or delay <= 0:
            return None
        dps = Fl(row['Quality_%d' % q])
        var = Fl(sp['DmgVariance'])
        avg = dps * delay / 1000.0
        lo = int(math.floor((1 - var / 2) * avg))          # client truncates the minimum
        hi = int(math.floor((1 + var / 2) * avg + 0.5))    # and rounds the maximum
        speed = delay / 1000.0
        return {'min': lo, 'max': hi, 'speed': speed, 'dps': round((lo + hi) / 2.0 / speed, 2)}


MATH = ItemMath(lambda t: T[t])
ERA_MATH = ItemMath(lambda t: fetch(t, ERA_BUILD, ERA_CACHE))


def item_record(sp, it, math_):
    """Compact item record; the same function runs on both builds so the diff compares computed values."""
    q = I(sp['OverallQualityID'])
    cls, sub, inv = I(it['ClassID']), I(it['SubclassID']), I(it['InventoryType'])
    rec = {'n': sp['Display_lang'], 'q': q, 'il': I(sp['ItemLevel']), 'c': cls, 'sc': sub, 'it': inv}
    for src, dst in (('RequiredLevel', 'rl'), ('Bonding', 'b'), ('MaxCount', 'mc'), ('Stackable', 'st'), ('SellPrice', 'sp'),
                     ('BuyPrice', 'bp'), ('ContainerSlots', 'cs'), ('StartQuestID', 'sq'), ('ItemDelay', 'dl'), ('AllowableClass', 'ac')):
        v = I(sp.get(src, it.get(src, 0)))
        if v and not (dst == 'st' and v == 1) and not (dst == 'ac' and v == -1):
            rec[dst] = v
    if sp['Description_lang']:
        rec['d'] = sp['Description_lang']
    if I(sp['RequiredSkill']):
        rec['rs'] = [I(sp['RequiredSkill']), I(sp['RequiredSkillRank'])]
    st = math_.stats(sp, q, inv)
    if st:
        rec['s'] = st
    ar = math_.armor(cls, sub, inv, I(sp['ItemLevel']), q, it)
    if ar:
        rec['ar'] = ar
    dm = math_.damage(cls, sub, sp, q, it)
    if dm:
        rec['dm'] = dm
    return rec


# ---------------------------------------------------------------- spells
spell_ids = sorted(set(SPELLNAME) | set(SPELL))
CREATED_BY = collections.defaultdict(list)   # item -> [(spell, count)]
REAGENT_FOR = collections.defaultdict(list)  # item -> [spell]
TAUGHT_BY = collections.defaultdict(list)    # spell -> [item]
USED_BY = collections.defaultdict(list)      # spell -> [item]
for iid, fxs in ITEMFX.items():
    for fx in fxs:
        sid = I(fx['SpellID'])
        if I(fx['TriggerType']) == 6:
            TAUGHT_BY[sid].append(iid)
        elif sid and sid != 402265:
            USED_BY[sid].append(iid)

spells = {}
for sid in spell_ids:
    name = SPELLNAME.get(sid, '')
    s = SPELL.get(sid, {})
    m = MISC.get(sid)
    rec = {'n': name}
    if s.get('NameSubtext_lang'):
        rec['r'] = s['NameSubtext_lang']
    if m:
        ic = icon(m['SpellIconFileDataID'])
        if ic:
            rec['ic'] = ic
        ct = CASTTIME.get(I(m['CastingTimeIndex']))
        if ct and I(ct['Base']) > 0:
            rec['ct'] = I(ct['Base'])
        rg = RANGE.get(I(m['RangeIndex']))
        if rg and Fl(rg['RangeMax_0']) > 0:
            rec['rg'] = Fl(rg['RangeMax_0'])
        dur = spell_duration_ms(sid)
        if dur:
            rec['du'] = dur
    d = render_desc(sid, s.get('Description_lang', ''))
    if d:
        rec['d'] = d
    ad = render_desc(sid, s.get('AuraDescription_lang', ''))
    if ad and ad != d:
        rec['ad'] = ad
    lv = LEVELS.get(sid)
    if lv and (I(lv['BaseLevel']) or I(lv['SpellLevel'])):
        rec['lv'] = I(lv['BaseLevel']) or I(lv['SpellLevel'])
    pw = [p for p in POWER.get(sid, []) if I(p['ManaCost']) or Fl(p['PowerCostPct'])]
    if pw:
        p = pw[0]
        rec['pw'] = [I(p['PowerType']), I(p['ManaCost']), Fl(p['PowerCostPct'])]
    cd = COOLDOWN.get(sid)
    if cd:
        rt = max(I(cd['RecoveryTime']), I(cd['CategoryRecoveryTime']))
        if rt > 0:
            rec['cd'] = rt
    rg = REAGENTS.get(sid)
    if rg:
        lst = []
        for i in range(8):
            r = I(rg['Reagent_%d' % i])
            if r > 0:
                lst.append([r, I(rg['ReagentCount_%d' % i]) or 1])
                REAGENT_FOR[r].append(sid)
        if lst:
            rec['rg_'] = lst
    for e in EFFECTS.get(sid, []):
        eff = I(e['Effect'])
        if eff == 24 and I(e['EffectItemType']):
            cnt = max(1, int(round(Fl(e['EffectBasePointsF']))))
            rec['cr'] = [I(e['EffectItemType']), cnt]
            CREATED_BY[I(e['EffectItemType'])].append((sid, cnt))
        elif eff in (53, 54, 92) and I(e['EffectMiscValue_0']) in ENCHANT:
            en = ENCHANT[I(e['EffectMiscValue_0'])]
            rec['en'] = [I(e['EffectMiscValue_0']), en['Name_lang']]
        elif eff == 36 and I(e['EffectTriggerSpell']):
            rec['ls'] = I(e['EffectTriggerSpell'])
    spells[sid] = rec

for sid, its in TAUGHT_BY.items():
    if sid in spells:
        spells[sid]['tb'] = sorted(set(its))
for sid, its in USED_BY.items():
    if sid in spells:
        spells[sid]['ub'] = sorted(set(its))

# skill line abilities
PROF_PRIMARY = [171, 164, 333, 202, 182, 165, 186, 393, 197]
PROF_SECONDARY = [185, 129, 356]
PROF_OTHER = [40]
PROF_IDS = PROF_PRIMARY + PROF_SECONDARY + PROF_OTHER
era_sla = {}
for r in E['SkillLineAbility']:
    era_sla.setdefault(I(r['Spell']), r)
era_reagents = {}
for r in E['SpellReagents']:
    era_reagents.setdefault(I(r['SpellID']), r)
era_created = {}
for r in E['SpellEffect']:
    if I(r['Effect']) == 24 and I(r['EffectItemType']):
        era_created.setdefault(I(r['SpellID']), I(r['EffectItemType']))
era_spell_ids = {I(r['ID']) for r in E['SpellName']}
era_item_ids = {I(r['ID']) for r in E['ItemSparse']}


def reagent_list(row):
    if not row:
        return []
    return sorted((I(row['Reagent_%d' % i]), I(row['ReagentCount_%d' % i])) for i in range(8) if I(row['Reagent_%d' % i]) > 0)


profs = {}
class_lines = collections.defaultdict(lambda: collections.defaultdict(list))  # class -> skillline -> [spell]
general_lines = collections.defaultdict(list)
for r in SLA:
    sid, sl = I(r['Spell']), I(r['SkillLine'])
    if sid not in spells or not spells[sid]['n']:
        continue
    line = SKILLLINE.get(sl)
    if not line:
        continue
    if sl in PROF_IDS:
        lo, hi = I(r['TrivialSkillLineRankLow']), I(r['TrivialSkillLineRankHigh'])
        entry = {'sl': sl, 'min': I(r['MinSkillLineRank']), 'lo': lo, 'hi': hi,
                 'cat': I(r['TradeSkillCategoryID']), 'acq': I(r['AcquireMethod'])}
        # The orange ("requires skill") threshold is not in SkillLineAbility in this client; recipe items carry it.
        req = [I(SPARSE[i]['RequiredSkillRank']) for i in TAUGHT_BY.get(sid, []) if i in SPARSE and I(SPARSE[i]['RequiredSkill']) == sl]
        if req:
            entry['req'] = max(req)
        elif entry['min'] > 1:
            entry['req'] = entry['min']
        if I(r['SupercedesSpell']):
            entry['sup'] = I(r['SupercedesSpell'])
        chg = []
        if sid not in era_spell_ids:
            entry['new'] = 1
        else:
            o = era_sla.get(sid)
            if o and (I(o['TrivialSkillLineRankLow']), I(o['TrivialSkillLineRankHigh'])) != (lo, hi):
                chg.append('skill-ups %s/%s -> %s/%s' % (o['TrivialSkillLineRankLow'], o['TrivialSkillLineRankHigh'], lo, hi))
            if reagent_list(era_reagents.get(sid)) != reagent_list(REAGENTS.get(sid)):
                chg.append('reagents')
            if era_created.get(sid) and spells[sid].get('cr') and era_created[sid] != spells[sid]['cr'][0]:
                chg.append('result')
        if chg:
            entry['chg'] = chg
        spells[sid]['sk'] = entry
        profs.setdefault(sl, []).append(sid)
    elif I(line['CategoryID']) == 7:
        mask = I(r['ClassMask'])
        cls = [c for c in CLASSES if mask & (1 << (c - 1))]
        if len(cls) == 1:
            class_lines[cls[0]][sl].append(sid)
        else:
            general_lines[sl].append(sid)
        spells[sid].setdefault('cl', []).append(sl)

for sid in spells:
    if sid not in era_spell_ids:
        spells[sid]['new'] = 1

spells = {k: v for k, v in spells.items() if v['n']}

# ---------------------------------------------------------------- items
ERA_SPARSE = by_id(E['ItemSparse'])
ERA_ITEM = by_id(E['Item'])


def parent_line(sl):
    row = SKILLLINE.get(sl)
    return I(row['ParentSkillLineID']) or sl if row and I(row['ParentSkillLineID']) else sl


DIFF_FIELDS = {'n': 'name', 'q': 'quality', 'il': 'item level', 'rl': 'required level', 'b': 'binding', 'mc': 'unique', 'st': 'stack size',
               'sp': 'sell price', 'cs': 'bag slots', 'dl': 'speed', 'ac': 'class restriction', 'rs': 'required skill', 's': 'stats',
               'ar': 'armor', 'dm': 'damage', 'it': 'slot'}

SETS_BY_ITEM = {}
sets = {}
for r in T['ItemSet']:
    sid = I(r['ID'])
    its = [I(r['ItemID_%d' % i]) for i in range(17) if I(r['ItemID_%d' % i]) in SPARSE]
    if not its:
        continue
    sets[sid] = {'n': r['Name_lang'], 'items': its, 'b': []}
    if I(r['RequiredSkill']):
        sets[sid]['rs'] = [I(r['RequiredSkill']), I(r['RequiredSkillRank'])]
    for it in its:
        SETS_BY_ITEM[it] = sid
for r in T['ItemSetSpell']:
    s = sets.get(I(r['ItemSetID']))
    if s and I(r['SpellID']) in spells:
        s['b'].append([I(r['Threshold']), I(r['SpellID'])])
for s in sets.values():
    s['b'].sort()

items = {}
new_items = 0
mod_items = 0
for iid, sp in SPARSE.items():
    it = ITEM.get(iid)
    if not it or not sp['Display_lang']:
        continue
    rec = item_record(sp, it, MATH)
    ic = icon(it['IconFileDataID'])
    if ic:
        rec['ic'] = ic
    lc = LIMITCAT.get(I(sp.get('LimitCategory', 0)))
    if lc:
        rec['lc'] = [lc['Name_lang'], I(lc['Quantity'])]
    fac = FACTION.get(I(sp.get('MinFactionID', 0)))
    if fac and I(sp.get('MinReputation', 0)):
        rec['rep'] = [fac['Name_lang'], I(sp['MinReputation'])]
    fx = []
    for f in ITEMFX.get(iid, []):
        sid = I(f['SpellID'])
        if sid in spells and sid != 402265:
            e = [I(f['TriggerType']), sid]
            if I(f['CoolDownMSec']) > 0:
                e.append(I(f['CoolDownMSec']))
            elif I(f['CategoryCoolDownMSec']) > 0:
                e.append(I(f['CategoryCoolDownMSec']))
            fx.append(e)
    if fx:
        rec['fx'] = fx
    if iid in SETS_BY_ITEM:
        rec['set'] = SETS_BY_ITEM[iid]
    if iid in CREATED_BY:
        rec['cb'] = sorted(set(s for s, _ in CREATED_BY[iid]))
    if iid in REAGENT_FOR:
        rec['rf'] = sorted(set(REAGENT_FOR[iid]))
    if iid not in era_item_ids:
        rec['new'] = 1
        new_items += 1
    elif iid in ERA_ITEM:
        old = item_record(ERA_SPARSE[iid], ERA_ITEM[iid], ERA_MATH)
        diffs = []
        for k, label in DIFF_FIELDS.items():
            a, b = old.get(k), rec.get(k)
            if k == 's':
                a, b = sorted(a or []), sorted(b or [])
            elif k == 'rs' and a and b:   # Forever moved requirements onto child skill lines (First Aid 129 -> 2942)
                a, b = [parent_line(a[0]), a[1]], [parent_line(b[0]), b[1]]
            if a != b:
                diffs.append(label)
        if diffs:
            rec['mod'] = diffs
            if old['n'] != rec['n']:
                rec['old'] = old['n']
            mod_items += 1
    items[iid] = rec

# ---------------------------------------------------------------- professions
prof_out = []
for sl in PROF_IDS:
    line = SKILLLINE.get(sl)
    if not line:
        continue
    cats = {}
    for sid in profs.get(sl, []):
        c = spells[sid]['sk']['cat']
        while c and c not in cats:
            row = TSC.get(c)
            if not row:
                break
            cats[c] = {'n': row['Name_lang'], 'p': I(row['ParentTradeSkillCategoryID']), 'o': I(row['OrderIndex'])}
            c = I(row['ParentTradeSkillCategoryID'])
    prof_out.append({'id': sl, 'n': line['DisplayName_lang'], 'ic': icon(line['SpellIconFileID']),
                     'kind': 'primary' if sl in PROF_PRIMARY else ('secondary' if sl in PROF_SECONDARY else 'other'),
                     'cats': cats, 'recipes': sorted(profs.get(sl, []), key=lambda s: (spells[s]['sk']['min'], spells[s]['n']))})

classes_out = []
for cid, cname in sorted(CLASSES.items()):
    lines = []
    for sl, sids in class_lines.get(cid, {}).items():
        lines.append({'id': sl, 'n': SKILLLINE[sl]['DisplayName_lang'], 'spells': sorted(set(sids), key=lambda s: (spells[s].get('lv', 0), spells[s]['n']))})
    lines.sort(key=lambda l: l['n'])
    classes_out.append({'id': cid, 'n': cname, 'lines': lines})
general_out = [{'id': sl, 'n': SKILLLINE[sl]['DisplayName_lang'], 'spells': sorted(set(sids), key=lambda s: spells[s]['n'])}
               for sl, sids in general_lines.items()]
general_out.sort(key=lambda l: l['n'])

# ---------------------------------------------------------------- zones
MAPS = {I(r['ID']): r for r in T['Map']}
zones = []
for r in T['AreaTable']:
    zones.append({'id': I(r['ID']), 'n': r['AreaName_lang'], 'm': I(r['ContinentID']), 'p': I(r['ParentAreaID']),
                  'lv': I(r['ExplorationLevel'])})
maps_out = {mid: {'n': m['MapName_lang'], 't': I(m['InstanceType'])} for mid, m in MAPS.items()}

# ---------------------------------------------------------------- meta
STAT_NAMES = {0: 'Mana', 1: 'Health', 3: 'Agility', 4: 'Strength', 5: 'Intellect', 6: 'Spirit', 7: 'Stamina',
              12: 'Defense Rating', 13: 'Dodge Rating', 14: 'Parry Rating', 15: 'Block Rating', 16: 'Hit Rating (melee)',
              17: 'Hit Rating (ranged)', 18: 'Hit Rating (spell)', 19: 'Crit Rating (melee)', 20: 'Crit Rating (ranged)',
              21: 'Crit Rating (spell)', 28: 'Haste Rating (melee)', 29: 'Haste Rating (ranged)', 30: 'Haste Rating (spell)',
              31: 'Hit Rating', 32: 'Critical Strike Rating', 35: 'Resilience', 36: 'Haste Rating', 37: 'Expertise Rating',
              38: 'Attack Power', 39: 'Ranged Attack Power', 40: 'Versatility', 41: 'Healing Power', 42: 'Spell Damage',
              43: 'Mana Regeneration', 44: 'Armor Penetration', 45: 'Spell Power', 46: 'Health Regeneration', 47: 'Spell Penetration',
              48: 'Block Value', 49: 'Mastery', 50: 'Bonus Armor', 51: 'Fire Resistance', 52: 'Frost Resistance', 53: 'Holy Resistance',
              54: 'Shadow Resistance', 55: 'Nature Resistance', 56: 'Arcane Resistance', 57: 'PvP Power', 71: 'Agility/Strength/Intellect',
              72: 'Agility/Strength', 73: 'Agility/Intellect', 74: 'Strength/Intellect'}
# Forever-only stat kinds (ids 83+). Names follow the ITEM_MOD_* GlobalStrings of this build in enum order; the
# mapping was inferred from item usage (e.g. Tome of Fiery Arcana carries 85, +fishing poles carry 117).
FOREVER_STATS = ['Physical Damage', 'Holy Damage', 'Fire Damage', 'Nature Damage', 'Frost Damage', 'Shadow Damage', 'Arcane Damage',
                 'Two-Handed Axes Skill', 'Two-Handed Maces Skill', 'Two-Handed Swords Skill', 'Axes Skill', 'Bows Skill', 'Crossbows Skill',
                 'Daggers Skill', 'Dual Wield Skill', 'Fist Weapons Skill', 'Guns Skill', 'Maces Skill', 'Polearms Skill', 'Staves Skill',
                 'Swords Skill', 'Thrown Skill', 'Wands Skill', 'Alchemy Skill', 'Blacksmithing Skill', 'Enchanting Skill', 'Engineering Skill',
                 'Jewelcrafting Skill', 'Leatherworking Skill', 'Herbalism Skill', 'Mining Skill', 'Skinning Skill', 'Cooking Skill',
                 'First Aid Skill', 'Fishing Skill', 'Tailoring Skill', 'Fire Piercing', 'Nature Piercing', 'Frost Piercing', 'Shadow Piercing',
                 'Arcane Piercing', 'Spell Resistance', 'Attack Power Vs Humanoids', 'Attack Power Vs Elementals', 'Attack Power Vs Demons',
                 'Attack Power Vs Undead', 'Attack Power Vs Dragonkin', 'Attack Power Vs Giants', 'Attack Power Vs Beasts',
                 'Attack Power Vs Mechanical', 'Spell Damage Vs Humanoids', 'Spell Damage Vs Elementals', 'Spell Damage Vs Demons',
                 'Spell Damage Vs Undead', 'Spell Damage Vs Dragonkin', 'Spell Damage Vs Giants', 'Spell Damage Vs Beasts',
                 'Spell Damage Vs Mechanical']
for i, n in enumerate(FOREVER_STATS):
    STAT_NAMES[83 + i] = n
INV_TYPES = {0: '', 1: 'Head', 2: 'Neck', 3: 'Shoulder', 4: 'Shirt', 5: 'Chest', 6: 'Waist', 7: 'Legs', 8: 'Feet', 9: 'Wrist', 10: 'Hands',
             11: 'Finger', 12: 'Trinket', 13: 'One-Hand', 14: 'Off Hand', 15: 'Ranged', 16: 'Back', 17: 'Two-Hand', 18: 'Bag', 19: 'Tabard',
             20: 'Chest', 21: 'Main Hand', 22: 'Off Hand', 23: 'Held In Off-hand', 24: 'Ammo', 25: 'Thrown', 26: 'Ranged', 27: 'Quiver', 28: 'Relic'}
meta = {
    'build': BUILD, 'eraBuild': ERA_BUILD, 'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
    'classes': CLASSES, 'itemClasses': ITEMCLASS,
    'itemSubClasses': {'%d_%d' % k: v for k, v in ITEMSUB.items()},
    'invTypes': INV_TYPES, 'stats': STAT_NAMES,
    'skillLines': {sl: r['DisplayName_lang'] for sl, r in SKILLLINE.items()},
    'counts': {'items': len(items), 'spells': len(spells), 'recipes': sum(len(p['recipes']) for p in prof_out),
               'sets': len(sets), 'zones': len(zones), 'newItems': new_items, 'modItems': mod_items,
               'newSpells': sum(1 for s in spells.values() if s.get('new')),
               'newRecipes': sum(1 for p in prof_out for s in p['recipes'] if spells[s]['sk'].get('new') and (spells[s].get('cr') or spells[s].get('en') or spells[s].get('rg_')))},
}


def dump(name, var, obj):
    path = os.path.join(DATA, name + '.js')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('window.%s=' % var)
        f.write(json.dumps(obj, separators=(',', ':'), ensure_ascii=False))
        f.write(';\n')
    print('  wrote %-14s %6d KB' % (name + '.js', os.path.getsize(path) // 1024))


# ---------------------------------------------------------------- snapshot + patch history
SNAP_ITEM_KEYS = ('n', 'q', 'il', 'rl', 'b', 'mc', 'st', 'sp', 'cs', 'ac', 'rs', 's', 'ar', 'dm', 'fx', 'set', 'c', 'sc', 'it', 'd')
SNAP_SPELL_KEYS = ('n', 'r', 'd', 'ad', 'lv', 'pw', 'ct', 'cd', 'rg_', 'cr', 'en', 'tb')
snapshot = {
    'build': BUILD, 'generated': meta['generated'],
    'items': {str(i): {k: r[k] for k in SNAP_ITEM_KEYS if k in r} for i, r in items.items()},
    'spells': {str(i): {k: r[k] for k in SNAP_SPELL_KEYS if k in r} for i, r in spells.items()},
    'recipes': {str(s): {'n': spells[s]['n'], 'sl': spells[s]['sk']['sl'], 'lo': spells[s]['sk']['lo'], 'hi': spells[s]['sk']['hi'],
                         'req': spells[s]['sk'].get('req'), 'rg': spells[s].get('rg_'), 'cr': spells[s].get('cr'), 'en': spells[s].get('en'),
                         'cat': spells[s]['sk']['cat']}
                for p in prof_out for s in p['recipes']},
}
snap_path = os.path.join(BUILDS, BUILD + '.json.gz')
with gzip.open(snap_path, 'wt', encoding='utf-8') as f:
    json.dump(snapshot, f, separators=(',', ':'), ensure_ascii=False)
with open(os.path.join(BUILDS, 'LATEST'), 'w') as f:
    f.write(BUILD + '\n')
print('  wrote snapshot builds/%s.json.gz (%d KB)' % (BUILD, os.path.getsize(snap_path) // 1024))
if SNAPSHOT_ONLY:
    print('Snapshot only; done.')
    sys.exit(0)


def load_snapshots():
    out = []
    for fn in os.listdir(BUILDS):
        if fn.endswith('.json.gz'):
            with gzip.open(os.path.join(BUILDS, fn), 'rt', encoding='utf-8') as f:
                out.append(json.load(f))
    out.sort(key=lambda s: vtuple(s['build']))
    return out


def diff_section(a, b):
    added = sorted([[k, b[k].get('n', '')] for k in b if k not in a], key=lambda x: x[1])
    removed = sorted([[k, a[k].get('n', '')] for k in a if k not in b], key=lambda x: x[1])
    changed = []
    for k in b:
        if k in a and a[k] != b[k]:
            fields = {f: [a[k].get(f), b[k].get(f)] for f in sorted(set(a[k]) | set(b[k])) if a[k].get(f) != b[k].get(f)}
            changed.append([k, b[k].get('n', ''), fields])
    changed.sort(key=lambda x: x[1])
    return {'added': added, 'removed': removed, 'changed': changed}


snaps = load_snapshots()
patches = []
for prev, cur in zip(snaps, snaps[1:]):
    patches.append({'from': prev['build'], 'to': cur['build'], 'date': cur['generated'],
                    'items': diff_section(prev['items'], cur['items']),
                    'spells': diff_section(prev['spells'], cur['spells']),
                    'recipes': diff_section(prev['recipes'], cur['recipes'])})
patches.reverse()
meta['builds'] = [s['build'] for s in snaps]

print('Writing site data')
dump('patches', 'FR_PATCHES', patches)
dump('meta', 'FR_META', meta)
dump('items', 'FR_ITEMS', items)
dump('spells', 'FR_SPELLS', spells)
dump('profs', 'FR_PROFS', prof_out)
dump('classes', 'FR_CLASSES', {'classes': classes_out, 'general': general_out})
dump('sets', 'FR_SETS', sets)
dump('zones', 'FR_ZONES', {'zones': zones, 'maps': maps_out})
print('Done:', json.dumps(meta['counts']))
