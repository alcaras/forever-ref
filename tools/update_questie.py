#!/usr/bin/env python3
"""Install or update Questie + QuestieDB in the beta AddOns folder from the newest GitHub bundle release.

Usage: python tools/update_questie.py [--force]
Looks at https://github.com/Questie/Questie/releases for the newest tag starting with "bundle/" (those zips contain
both addons), downloads it when its tag differs from the installed one (recorded in AddOns/Questie/.forever-ref-tag),
and replaces AddOns/Questie and AddOns/QuestieDB.
"""
import io, json, os, shutil, sys, urllib.request, zipfile

ADDONS = r'D:\Games\World of Warcraft\_classic_beta_\Interface\AddOns'
API = 'https://api.github.com/repos/Questie/Questie/releases?per_page=20'
UA = {'User-Agent': 'forever-ref'}

rels = json.loads(urllib.request.urlopen(urllib.request.Request(API, headers=UA), timeout=60).read())
bundle = next((r for r in rels if r['tag_name'].startswith('bundle/')), None)
if not bundle:
    raise SystemExit('no bundle release found')
asset = next((a for a in bundle['assets'] if a['name'].endswith('.zip')), None)
tag_file = os.path.join(ADDONS, 'Questie', '.forever-ref-tag')
installed = open(tag_file).read().strip() if os.path.exists(tag_file) else None
print('newest bundle:', bundle['tag_name'], bundle['published_at'][:10], '| installed:', installed or 'none')
if installed == bundle['tag_name'] and '--force' not in sys.argv:
    print('already up to date')
    raise SystemExit(0)
print('downloading', asset['name'], asset['size'] // 1048576, 'MB')
data = urllib.request.urlopen(urllib.request.Request(asset['browser_download_url'], headers=UA), timeout=600).read()
z = zipfile.ZipFile(io.BytesIO(data))
tops = {n.split('/')[0] for n in z.namelist()}
if not {'Questie', 'QuestieDB'} <= tops:
    raise SystemExit('unexpected zip layout: %s' % tops)
for top in ('Questie', 'QuestieDB'):
    dest = os.path.join(ADDONS, top)
    if os.path.exists(dest):
        shutil.rmtree(dest)
z.extractall(ADDONS, [n for n in z.namelist() if n.split('/')[0] in ('Questie', 'QuestieDB')])
open(tag_file, 'w').write(bundle['tag_name'])
print('installed', bundle['tag_name'], 'into', ADDONS)
