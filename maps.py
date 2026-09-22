#!/usr/bin/env python3
"""Extract world map images for the Forever build.

Reads the UiMap* tables, downloads the map tile files (BLP) through wago.tools' CASC endpoint,
stitches them and writes site/maps/<uiMapId>.jpg plus site/data/maps.js (map tree, child map
rectangles for clickable overlays, and the AreaTable id of each map).

Usage: python maps.py [--build 1.60.1.X] [--refresh]
"""
import csv, io, json, os, sys, urllib.request

from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
UA = {'User-Agent': 'Mozilla/5.0 forever-ref/1.0'}
BUILD = '1.60.1.69913'
if '--build' in sys.argv:
    BUILD = sys.argv[sys.argv.index('--build') + 1]
elif os.path.exists(os.path.join(ROOT, 'builds', 'LATEST')):
    BUILD = open(os.path.join(ROOT, 'builds', 'LATEST')).read().strip()
REFRESH = '--refresh' in sys.argv
CACHE = os.path.join(ROOT, 'cache', BUILD)
TILES = os.path.join(ROOT, 'cache', 'tiles')
OUT = os.path.join(ROOT, 'site', 'maps')
DATA = os.path.join(ROOT, 'site', 'data')
for d in (CACHE, TILES, OUT, DATA):
    os.makedirs(d, exist_ok=True)


def get(url, path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()
        with open(path, 'wb') as f:
            f.write(data)
    return open(path, 'rb').read()


def table(name):
    path = os.path.join(CACHE, name + '.csv')
    get(f'https://wago.tools/db2/{name}/csv?build={BUILD}', path)
    with open(path, encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    if rows and 'errors' in rows[0]:
        raise SystemExit(f'{name} not available for {BUILD}')
    return rows


def I(s):
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return 0


def F(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return 0.0


print('Build', BUILD)
uimaps = {I(r['ID']): r for r in table('UiMap')}
art_of = {}
for r in table('UiMapXMapArt'):
    if I(r['PhaseID']) == 0 or I(r['UiMapID']) not in art_of:
        art_of[I(r['UiMapID'])] = I(r['UiMapArtID'])
style_of = {I(r['ID']): I(r['UiMapArtStyleID']) for r in table('UiMapArt')}
layers = {(I(r['UiMapArtStyleID']), I(r['LayerIndex'])): r for r in table('UiMapArtStyleLayer')}
tiles = {}
for r in table('UiMapArtTile'):
    if I(r['LayerIndex']) == 0:
        tiles.setdefault(I(r['UiMapArtID']), []).append((I(r['RowIndex']), I(r['ColIndex']), I(r['FileDataID'])))
assign = {}
for r in table('UiMapAssignment'):
    m = I(r['UiMapID'])
    if m not in assign or I(r['OrderIndex']) < I(assign[m]['OrderIndex']):
        assign[m] = r

maps = {}
for mid, r in sorted(uimaps.items()):
    rec = {'n': r['Name_lang'], 'p': I(r['ParentUiMapID']), 't': I(r['Type'])}
    a = assign.get(mid)
    if a:
        rec['area'] = I(a['AreaID'])
        rec['map'] = I(a['MapID'])
    art = art_of.get(mid)
    if art and art in tiles and (style_of.get(art), 0) in layers:
        lay = layers[(style_of[art], 0)]
        W, H, tw, th = I(lay['LayerWidth']), I(lay['LayerHeight']), I(lay['TileWidth']), I(lay['TileHeight'])
        out = os.path.join(OUT, f'{mid}.jpg')
        if REFRESH or not os.path.exists(out):
            rows = max(t[0] for t in tiles[art]) + 1
            cols = max(t[1] for t in tiles[art]) + 1
            canvas = Image.new('RGB', (cols * tw, rows * th))
            for row, col, fdid in tiles[art]:
                blp = get(f'https://wago.tools/api/casc/{fdid}?version={BUILD}', os.path.join(TILES, f'{fdid}.blp'))
                try:
                    img = Image.open(io.BytesIO(blp)).convert('RGB')
                except Exception as e:
                    print('  tile decode failed', mid, fdid, e)
                    continue
                canvas.paste(img.resize((tw, th)) if img.size != (tw, th) else img, (col * tw, row * th))
            canvas.crop((0, 0, W, H)).save(out, 'JPEG', quality=85, optimize=True)
            print(f'  {mid:5d} {r["Name_lang"]:28s} {W}x{H} from {len(tiles[art])} tiles')
        rec['img'] = 1
        rec['w'], rec['h'] = W, H
    maps[mid] = rec


def ui_transform(a):
    """world (x north, y west) -> map UI fraction (u right, v down) for one UiMapAssignment row."""
    minx, miny, maxx, maxy = F(a['Region_0']), F(a['Region_1']), F(a['Region_3']), F(a['Region_4'])
    umin, vmin, umax, vmax = F(a['UiMin_0']), F(a['UiMin_1']), F(a['UiMax_0']), F(a['UiMax_1'])

    def f(x, y):
        u = umin + (maxy - y) / (maxy - miny) * (umax - umin) if maxy != miny else 0
        v = vmin + (maxx - x) / (maxx - minx) * (vmax - vmin) if maxx != minx else 0
        return u, v
    return f


for mid, rec in maps.items():
    kids = []
    if mid in assign:
        f = ui_transform(assign[mid])
        for cid, crec in maps.items():
            if crec['p'] != mid or cid not in assign:
                continue
            c = assign[cid]
            l, t = f(F(c['Region_3']), F(c['Region_4']))
            r_, b = f(F(c['Region_0']), F(c['Region_1']))
            kids.append([cid, round(min(l, r_), 4), round(min(t, b), 4), round(max(l, r_), 4), round(max(t, b), 4)])
    if kids:
        rec['kids'] = kids

with open(os.path.join(DATA, 'maps.js'), 'w', encoding='utf-8') as f:
    f.write('window.FR_MAPS=' + json.dumps({'build': BUILD, 'maps': maps}, separators=(',', ':'), ensure_ascii=False) + ';\n')
n = sum(1 for m in maps.values() if m.get('img'))
print(f'Done: {len(maps)} maps, {n} with images, {sum(os.path.getsize(os.path.join(OUT, x)) for x in os.listdir(OUT)) // 1024} KB of jpg')
