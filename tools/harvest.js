// Wowhead Forever zone harvest, run inside the browser pane on a www.wowhead.com/forever/... page.
// Paste the whole file into one javascript_tool call once per page load (it only defines functions on window),
// then call the steps. Every step returns within ~40 s (the tool times out at 45 s); long lists are chunked.
//
//   await FH.zone(16593)                 -> window.FH.list  (the zone's quest listview, all factions)
//   FH.hordeIds()                        -> ids with side 2 (Horde) or 3 (both)
//   await FH.quests(FH.hordeIds(), 0)    -> parses 30 quest pages starting at offset 0; repeat with 30, 60, ...
//   FH.npcIds()                          -> start/end NPC ids of the parsed quests
//   await FH.npcs(FH.npcIds(), 0)        -> 30 NPC pages per call (coordinates from g_mapperData)
//   FH.save('zone-16593', FH.list)       -> form POST to tools/recv.py (port 8790) -> cache/wowhead/zone-16593.json
//
// Wowhead rate-limits bursts (403 after ~100 quick pages, lasting 10+ minutes): 0.9 s between pages and at most
// ~90 pages before a few minutes' pause has been safe. A 403 stops the batch; FH.fail lists what failed.
window.FH = window.FH || { list: null, qi: {}, npc: {}, fail: [] };
(function (FH) {
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  // balanced-bracket slice of the `data: [...]` literal after `new Listview({ template: 'quest'`; the literal is JS, not JSON
  FH.listview = function (html, template) {
    let t = html.indexOf("template: '" + template + "'"); if (t < 0) t = html.indexOf("template:'" + template + "'");
    if (t < 0) return null;
    const lv = html.lastIndexOf('new Listview(', t), d = html.indexOf('data:', lv), i = html.indexOf('[', d);
    let depth = 0, inStr = null, esc = false, j = i;
    for (; j < html.length; j++) {
      const c = html[j];
      if (inStr) { if (esc) esc = false; else if (c === '\\') esc = true; else if (c === inStr) inStr = null; continue; }
      if (c === '"' || c === "'") { inStr = c; continue; }
      if (c === '[' || c === '{') depth++;
      else if (c === ']' || c === '}') { depth--; if (depth === 0) break; }
    }
    return Function('return ' + html.slice(i, j + 1))();
  };

  FH.zone = async function (area) {
    const html = await (await fetch('/forever/zone=' + area)).text();
    FH.list = FH.listview(html, 'quest');
    return { area, quests: FH.list ? FH.list.length : 0, horde: FH.list ? FH.hordeIds().length : 0 };
  };
  FH.hordeIds = () => (FH.list || []).filter(q => q.side === 2 || q.side === 3).map(q => q.id);

  // quest page: infobox markup (Start / End / Side / Requires level) and the series table (chain rows)
  FH.parseQuest = function (html, id) {
    const r = {};
    const ib = html.match(/printHtml\("([\s\S]*?)",\s*"infobox-contents-0"/);
    if (ib) {
      const t = ib[1];
      const st = t.match(/Start:\s*\[url=[^\]]*?(npc|object|item)=(\d+)/); if (st) r.start = [st[1], +st[2]];
      const en = t.match(/End:\s*\[url=[^\]]*?(npc|object|item)=(\d+)/); if (en) r.end = [en[1], +en[2]];
      const sd = t.match(/Side:\s*(?:\[[^\]]*\])?([A-Za-z]+)/); if (sd) r.side = sd[1];
      const rl = t.match(/Requires level (\d+)/); if (rl) r.rl = +rl[1];
    }
    const se = html.match(/<table class="series">([\s\S]*?)<\/table>/);
    if (se) {
      r.chain = se[1].split(/<tr[\s>]/).slice(1).map(row => {
        const ids = [...row.matchAll(/quest=(\d+)/g)].map(m => +m[1]).filter((v, k, a) => a.indexOf(v) === k);
        return ids.length ? ids : [id];   // the current quest's own row has no link
      });
    }
    return r;
  };

  async function batch(ids, offset, store, path, parse) {
    const slice = ids.slice(offset, offset + 30);
    const t0 = Date.now();
    for (const id of slice) {
      if (store[id]) continue;
      if (Date.now() - t0 > 38000) break;   // stay under the tool's 45 s limit
      try {
        const res = await fetch(path + id);
        if (res.status !== 200) { FH.fail.push([id, res.status]); if (res.status === 403) break; continue; }
        store[id] = parse(await res.text(), id);
      } catch (e) { FH.fail.push([id, String(e)]); }
      await sleep(900);
    }
    return { offset, next: offset + 30, of: ids.length, have: Object.keys(store).length, missing: ids.filter(i => !store[i]).length, fail: FH.fail.slice(-5) };
  }
  FH.quests = (ids, offset) => batch(ids, offset || 0, FH.qi, '/forever/quest=', FH.parseQuest);

  FH.npcIds = () => {
    const s = new Set();
    for (const q of Object.values(FH.qi)) for (const k of ['start', 'end']) if (q[k] && q[k][0] === 'npc') s.add(q[k][1]);
    return [...s];
  };
  // NPC page: g_mapperData = { "<area>": [ { coords: [[x, y], ...] } ] }
  FH.parseNpc = function (html) {
    const out = {};
    const m = html.match(/g_mapperData\s*=\s*(\{[\s\S]*?\});\s*\n/);
    if (m) {
      const d = Function('return ' + m[1])();
      for (const [zone, arr] of Object.entries(d)) {
        const pts = [];
        for (const e of (arr || [])) for (const c of (e.coords || [])) pts.push([+(+c[0]).toFixed(1), +(+c[1]).toFixed(1)]);
        if (pts.length) out[zone] = pts.slice(0, 12);
      }
    }
    const nm = html.match(/<title>([^<]*?) - NPC/); if (nm) out._n = nm[1];
    return out;
  };
  FH.npcs = (ids, offset) => batch(ids, offset || 0, FH.npc, '/forever/npc=', FH.parseNpc);

  // Wowhead pages set upgrade-insecure-requests, so fetch() to http://localhost is blocked; a form POST navigates
  // the tab away (top-level navigation is not upgraded). Re-inject this file after navigating back.
  FH.save = function (name, data) {
    const f = document.createElement('form'); f.method = 'POST'; f.action = 'http://localhost:8790/save?name=' + encodeURIComponent(name);
    const i = document.createElement('input'); i.type = 'hidden'; i.name = 'data'; i.value = JSON.stringify(data); f.appendChild(i);
    document.body.appendChild(f); f.submit();
    return name + ': ' + i.value.length + ' bytes';
  };
})(window.FH);
'FH ready'
