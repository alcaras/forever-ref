# forever-ref

A static reference site for WoW Forever built purely from the game client's database tables
(items, spells, profession recipes, item sets, zones), with a diff against Classic Era.

## How it works

1. `build.py` downloads the DB2 tables for the pinned Forever build from
   `https://wago.tools/db2/<Table>/csv?build=1.60.1.69913` into `cache/` (and the Classic Era
   build into `cache/era/`). Downloads are cached; `--refresh` re-downloads.
2. It joins the tables, computes item stats / armor / damage with the client's own formulas
   (RandPropPoints, ItemDamage*, ItemArmor* tables), renders spell tooltip text
   (`$s1`, `$d`, `$o1`, `${...}` tokens), and writes compact data files to `site/data/*.js`.
3. `site/index.html` + `site/app.js` is a hash-routed single page app that works from `file://`
   and from any static host such as GitHub Pages.

```bash
python build.py            # rebuild site/data for the pinned build (cached CSVs)
python build.py --latest   # newest Forever build listed by wago.tools
python maps.py             # stitch world map images into site/maps/ (needs Pillow)
python validate.py         # compare a sample of items against Wowhead Forever tooltips
python -m http.server 8766 --directory site
```

Every build writes `builds/<build>.json.gz`, a snapshot of the comparable data. Consecutive
snapshots are diffed into the **Patches** page, so each new beta build shows what changed in
items, spells and recipes. `builds/` is committed; `cache/` and `site/data/` are not.

## GitHub Pages

`.github/workflows/pages.yml` runs on push, daily, and on demand: it builds the latest Forever
build, commits any new snapshot to `builds/`, and deploys `site/` to GitHub Pages. Map images are
committed under `site/maps/` because they rarely change; re-run `maps.py` when they do.

To pin a build instead, change `DEFAULT_BUILD` in `build.py` (the wago.tools build list is at
`https://wago.tools/api/builds`, product `wow_classic_beta`). Column checks in `fetch()` fail
loudly when a table layout changes.

## What is and is not in the client

| Content | Source |
|---|---|
| Items, computed stats, armor, damage, sell price, requirements | ItemSparse, Item, RandPropPoints, ItemDamage*, ItemArmor* |
| Use / equip / proc effects | ItemEffect, ItemXItemEffect, Spell |
| Recipes, reagents, skill-up thresholds, categories | SkillLineAbility, SpellReagents, SpellEffect, TradeSkillCategory |
| Which recipe item teaches a recipe | ItemEffect trigger type 6 |
| Item sets and bonuses | ItemSet, ItemSetSpell |
| Class abilities by skill line | SkillLineAbility (category 7), SpellLevels, SpellPower |
| Zones and subzones | AreaTable, Map |
| Icons | ManifestInterfaceData (FileDataID to icon name), served from Wowhead's CDN |

Not in the client and therefore missing: quest text and objectives, NPC positions, drop rates,
vendor stock, trainer lists, zone level ranges, durability. The orange "learn at" skill of a
recipe is only known when a recipe item carries it; trainer-taught recipes show `?`.

## Findings worth knowing

- Forever uses the modern rating system in tooltips: `+20 Hit`, `+28 Critical Strike`.
- Bows, guns and crossbows use the two-hand damage table (verified against Wowhead).
- Weapon damage: min is truncated, max is rounded, DPS shown is derived from the rounded range.
- Stat kinds 83 and up exist only in Forever (school-specific spell damage, weapon and profession
  skill bonuses, attack power versus creature types). Wowhead does not show them yet. The names
  here follow the client's `ITEM_MOD_*` string table in enum order and are inferred, marked `*`.
- Classic Era stores stat values, armor and damage directly on the item rows; Forever computes
  them from item level. The diff therefore compares computed results, not raw columns.
