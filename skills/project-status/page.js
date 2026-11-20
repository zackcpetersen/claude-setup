// Status page script. build.py inlines this file, page.css and the data into template.html.
// Pages: #home (also #overview and an empty hash), #inbox, #inbox/<hid>, #projects, #prs, #stats (also #stats/<me|team>/<30|90>),
// #p-<id>, #waiting (also #people), #delivered, #other (also #oneoffs). Unknown hashes show home.
// Every number and date is worked out in derive.py; this file only lays the data out.
const D = JSON.parse(document.getElementById('data').textContent);
const C = D.config || {};
const P = D.projects || [], W = D.waiting_on || [], O = D.one_offs || [];
const I = D.inbox || {items: [], snoozed: [], done_today: [], open: 0, effort: '0m'};
const ITEMS = I.items || [];
const STRIP = D.strip || {};
const CAP = (C.inbox && C.inbox.cap) || 7, HOME_N = (C.inbox && C.inbox.home_count) || 3;
const ST = D.stats || null, GROUPS = (ST && ST.groups) || {}, HAS_STATS = !!ST && Object.keys(GROUPS).length > 0;
const PIPE = D.pipeline || null, TL = D.timeline || {events: [], more: 0, days: 21}, WV = D.waiting || {rows: [], scale_days: 14};
const DLV = D.delivered || [], JOBS = D.jobs || {}, PTL = D.project_timelines || {}, UNL = D.unlinked || [];
const PILLS_PER_STAGE = 6;
const SVG = 'http://www.w3.org/2000/svg';
const today = D.today || (D.as_of || '').slice(0, 10);
const BASE_TITLE = C.title || document.title || 'Project Status';
const $ = id => document.getElementById(id);

// ---------- helpers ----------
function h(tag, attrs, ...kids){
  const e = document.createElement(tag);
  for (const k in (attrs || {})) { if (attrs[k] != null && attrs[k] !== false) e.setAttribute(k, attrs[k]); }
  for (const c of kids.flat(3)) { if (c == null || c === false) continue; e.append(c.nodeType ? c : document.createTextNode(String(c))); }
  return e;
}
function s(tag, attrs, ...kids){
  const e = document.createElementNS(SVG, tag);
  for (const k in (attrs || {})) { if (attrs[k] != null) e.setAttribute(k, attrs[k]); }
  for (const c of kids.flat(2)) { if (c == null) continue; e.append(c.nodeType ? c : document.createTextNode(String(c))); }
  return e;
}
function ring(pct, size){
  const sw = size >= 40 ? Math.round(size / 9) : 3, r = (size - sw) / 2, c = 2 * Math.PI * r, p = Math.max(0, Math.min(100, pct || 0));
  const g = s('svg', {class: 'ring', width: size, height: size, viewBox: `0 0 ${size} ${size}`, role: 'img', 'aria-label': p + ' percent done'});
  g.style.flex = 'none';
  g.append(s('circle', {cx: size/2, cy: size/2, r, fill: 'none', stroke: 'var(--track)', 'stroke-width': sw}));
  g.append(s('circle', {cx: size/2, cy: size/2, r, fill: 'none', stroke: 'var(--accent)', 'stroke-width': sw, 'stroke-linecap': 'round', 'stroke-dasharray': `${c * p / 100} ${c}`, transform: `rotate(-90 ${size/2} ${size/2})`}));
  if (size >= 40) { const fs = Math.round(size * .28); g.append(s('text', {x: size/2, y: size/2 + fs * .36, 'text-anchor': 'middle', 'font-size': fs, 'font-weight': 700, fill: 'var(--strong)'}, p + '%')); }
  return g;
}
// A count of things that need the user is not late, so the badge is neutral ink on gray.
function badge(n){ return n > 0 ? h('span', {class: 'badge', title: n + ' open item' + (n > 1 ? 's' : '') + ' for you', 'aria-label': n + ' open item' + (n > 1 ? 's' : '') + ' need you'}, n) : null; }
const ORDER = ['done', 'prog', 'wait', 'block', 'none'];
const LABEL = {done: 'Done', prog: 'In progress', wait: 'Waiting', block: 'Blocked', none: 'Not started'};
function key(st){ st = (st || '').toLowerCase(); return st === 'done' ? 'done' : st === 'in progress' ? 'prog' : st === 'waiting' ? 'wait' : st === 'blocked' ? 'block' : 'none'; }
function tally(items){ const t = {done: 0, prog: 0, wait: 0, block: 0, none: 0}; items.forEach(i => t[key(i.state)]++); return t; }
function sbar(t){
  const n = ORDER.reduce((a, k) => a + t[k], 0) || 1;
  return h('div', {class: 'sbar', role: 'img', 'aria-label': ORDER.filter(k => t[k]).map(k => t[k] + ' ' + LABEL[k].toLowerCase()).join(', ')}, ORDER.filter(k => t[k]).map(k => { const e = h('div', {class: 'seg ' + k}); e.style.width = (100 * t[k] / n) + '%'; return e; }));
}
function legend(t){ return h('div', {class: 'legend'}, ORDER.filter(k => t[k]).map(k => h('span', {}, h('span', {class: 'dot ' + k}), h('b', {}, t[k]), LABEL[k]))); }
const allItems = p => (p.breakdown || []).flatMap(g => g.items || []);
// Days from the local "today" the build worked out (not the UTC date of as_of).
function days(d){ if (!/^\d{4}-\d\d-\d\d/.test(d || '') || !today) return null; return Math.round((Date.parse(d.slice(0, 10)) - Date.parse(today)) / 864e5); }
function when(d){ const n = days(d); return n == null ? '' : n === 0 ? 'today' : n > 0 ? 'in ' + n + ' day' + (n > 1 ? 's' : '') : (-n) + ' day' + (n < -1 ? 's' : '') + ' late'; }
function isLate(d){ const n = days(d); return n != null && n < 0; }
function dueChip(d, word){ if (!d) return null; const n = days(d); return h('span', {class: 'chip' + (n != null && n < 0 ? ' is-late' : '')}, (word || 'Due') + ' ' + d + (when(d) ? ' (' + when(d) + ')' : '')); }
function statusKey(st){ return /risk|block/i.test(st || '') ? 'block' : /wait/i.test(st || '') ? 'wait' : /not started/i.test(st || '') ? 'none' : /progress/i.test(st || '') ? 'prog' : 'done'; }
function statusChip(st){ if (!st) return null; return h('span', {class: 'chip'}, h('span', {class: 'dot ' + statusKey(st)}), st); }
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function md(d){ if (!/^\d{4}-\d\d-\d\d/.test(d || '')) return d || ''; return MON[+d.slice(5, 7) - 1] + ' ' + (+d.slice(8, 10)); }
function addDays(d, n){ const t = new Date(Date.parse(d.slice(0, 10)) + n * 864e5); return t.toISOString().slice(0, 10); }
function weekday(d){ try { return new Intl.DateTimeFormat('en-US', {weekday: 'long', timeZone: 'UTC'}).format(Date.parse(d)); } catch (e) { return ''; } }
const byId = id => P.find(p => p.id === id);
const inboxOf = id => ITEMS.filter(i => i.project_id === id);
const openOff = O.filter(o => key(o.state) !== 'done');
const offNeeds = openOff.filter(o => o.needs_me).length;
function meta(parts){ const out = []; parts.filter(Boolean).forEach((x, i) => { if (i) out.push(' · '); out.push(x); }); return out; }
function plural(n, word){ return n + ' ' + word + (n === 1 ? '' : 's'); }
function clock(iso){
  const t = Date.parse(iso || ''); if (isNaN(t)) return '';
  const o = {hour: '2-digit', minute: '2-digit', hour12: false};
  try { return new Intl.DateTimeFormat([], Object.assign({timeZone: D.tz}, o)).format(t); } catch (e) { return new Intl.DateTimeFormat([], o).format(t); }
}
function store(k, v){ try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } return null; }
function pct(n, d){ return d > 0 ? Math.max(0, Math.min(100, 100 * n / d)) : 0; }
function fill(cls, width, extra){ const e = h('div', Object.assign({class: cls}, extra || {})); e.style.width = width + '%'; return e; }

// ---------- links on every mention ----------
// Links from data open only when they are http or https; anything else shows as plain text.
const safe = u => typeof u === 'string' && /^https?:\/\//i.test(u.trim()) ? u.trim() : null;
function xa(url, attrs, ...kids){ return safe(url) ? h('a', Object.assign({href: safe(url), target: '_blank', rel: 'noopener'}, attrs || {}), kids) : h('span', attrs || {}, kids); }
const ICON_LINK = 'M14 3h7v7h-2V6.4l-8.3 8.3-1.4-1.4L17.6 5H14zM5 5h6v2H7v10h10v-4h2v6H5z';
function icon(path, size){ return s('svg', {viewBox: '0 0 24 24', width: size || 12, height: size || 12, 'aria-hidden': 'true'}, s('path', {d: path})); }
// Segments from derive.link_mentions. Inside a row that is already a link, mentions become text plus a trailing icon link.
function parts(segs, inLink){
  if (!inLink) return segs.map(x => safe(x.url) ? xa(x.url, {}, x.text) : x.text);
  return segs.map(x => x.text);
}
function mentionIcons(segs){
  return (segs || []).filter(x => safe(x.url)).map(x => h('a', {class: 'mlink', href: safe(x.url), target: '_blank', rel: 'noopener', title: 'Open ' + x.text, 'aria-label': 'Open ' + x.text}, icon(ICON_LINK)));
}
function txt(obj, f, inLink){ const segs = obj && obj[f + '_parts']; return segs ? parts(segs, inLink) : (obj ? obj[f] : ''); }
function refNode(ref, segs){
  if (!ref) return null; let m;
  if (segs) return parts(segs, false);
  if (C.tracker_url && /^[A-Z][A-Z0-9]+-\d+$/.test(ref)) return h('a', {href: C.tracker_url + ref, target: '_blank', rel: 'noopener'}, ref);
  if (C.github_org && (m = /^([a-z][a-z0-9-]+)\s+#?(\d+)$/.exec(ref))) return h('a', {href: `https://github.com/${C.github_org}/${m[1]}/pull/${m[2]}`, target: '_blank', rel: 'noopener'}, ref);
  if (safe(ref)) return xa(ref, {}, 'link');
  return ref;
}

// ---------- shared pieces ----------
function tile(title, metaNode, ...kids){
  return h('section', {class: 'tile'}, h('div', {class: 'tile-h'}, h('h2', {}, title), metaNode == null ? null : typeof metaNode === 'string' ? h('span', {class: 'tile-m'}, metaNode) : metaNode), kids);
}
// items: [{label, on, href|onclick, disabled, title}]
function segmented(label, items){
  return h('div', {class: 'segd', role: 'group', 'aria-label': label}, items.map(it => {
    if (it.href) return h('a', {href: it.disabled ? null : it.href, 'aria-current': it.on ? 'true' : null, 'aria-disabled': it.disabled ? 'true' : null, title: it.title || null}, it.label);
    const b = h('button', {type: 'button', 'aria-pressed': it.on ? 'true' : 'false', 'aria-disabled': it.disabled ? 'true' : null, title: it.title || null}, it.label);
    if (!it.disabled) b.addEventListener('click', it.onclick);
    return b;
  }));
}
function chip(text, cls, attrs){ return h('span', Object.assign({class: 'chip' + (cls ? ' ' + cls : '')}, attrs || {}), text); }

// ---------- charts: drawn at their container's width, redrawn only on a real width change ----------
let CHARTS = [];
function chart(name, draw, data){ const el = h('div', {class: 'chart', 'data-chart': name}); CHARTS.push({el, draw, data, w: 0}); return el; }
function chartWidth(el){ return Math.max(240, Math.floor(el.getBoundingClientRect().width || el.clientWidth || 0)); }
function drawCharts(force){
  CHARTS = CHARTS.filter(c => c.el.isConnected);
  CHARTS.forEach(c => { const w = chartWidth(c.el); if (force || Math.abs(w - c.w) > 40) { c.w = w; c.el.replaceChildren(c.draw(c.data, w)); } });
}
function niceMax(m){ for (const v of [4, 6, 8, 10, 12, 16, 20, 24, 30, 40, 60, 80, 100, 120, 160, 200]) if (v >= m) return v; return Math.ceil(m / 100) * 100; }
function spark(values){
  const pts0 = (values || []).map((v, i) => [i, v]).filter(p => p[1] != null);
  const w = 110, hgt = 38, pad = 4;
  const svg = s('svg', {class: 'sp-svg', viewBox: `0 0 ${w} ${hgt}`, preserveAspectRatio: 'none', 'aria-hidden': 'true'});
  if (pts0.length < 2) return svg;
  const vs = pts0.map(p => p[1]), mx = Math.max(...vs), mn = Math.min(...vs), n = (values.length - 1) || 1;
  const pts = pts0.map(p => [pad + p[0] * (w - 2 * pad) / n, pad + (hgt - 2 * pad) * (1 - (p[1] - mn) / ((mx - mn) || 1))]);
  const d = pts.map((q, i) => (i ? 'L' : 'M') + q[0].toFixed(1) + ',' + q[1].toFixed(1)).join('');
  const L = pts[pts.length - 1];
  svg.append(s('path', {class: 'sp-a', d: `${d}L${L[0].toFixed(1)},${hgt}L${pts[0][0].toFixed(1)},${hgt}Z`}), s('path', {class: 'sp-l', d}),
    s('circle', {class: 'sp-d', cx: L[0].toFixed(1), cy: L[1].toFixed(1), r: 3.5}));
  return svg;
}
// Merged per week: gridlines at 0, half and max, every third week labeled, the current week highlighted.
function colBars(data, W){
  const v = data.values, labels = data.labels, H = 190, pl = 28, pr = 6, pt = 18, pb = 22, iw = W - pl - pr, ih = H - pt - pb;
  const mx = niceMax(Math.max(1, ...v)), n = v.length || 1, slot = iw / n, bw = Math.max(6, Math.min(40, slot - 8));
  const svg = s('svg', {class: 'th-svg', viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', 'aria-label': data.aria});
  for (const t of [0, mx / 2, mx]) {
    const y = pt + ih - ih * t / mx;
    svg.append(s('line', {class: 'th-grid', x1: pl, x2: W - pr, y1: y, y2: y}), s('text', {class: 'th-axis', x: pl - 6, y: y + 4, 'text-anchor': 'end'}, String(t)));
  }
  v.forEach((x, i) => {
    const bh = ih * x / mx, X = pl + i * slot + (slot - bw) / 2, Y = pt + ih - bh, r = Math.min(4, bh, bw / 2), last = i === n - 1;
    const tip = 'Week of ' + md(labels[i]) + ': ' + x + ' merged';
    if (bh > 0) svg.append(s('path', {class: 'th-bar' + (last ? ' is-now' : ''), d: `M${X},${pt + ih}V${Y + r}Q${X},${Y} ${X + r},${Y}H${X + bw - r}Q${X + bw},${Y} ${X + bw},${Y + r}V${pt + ih}Z`}));
    svg.append(s('rect', {class: 'th-hit', x: pl + i * slot, y: pt, width: slot, height: ih, 'data-tip': tip}, s('title', {}, tip)));
    if (i % 3 === 0) svg.append(s('text', {class: 'th-axis', x: X + bw / 2, y: H - 5, 'text-anchor': 'middle'}, md(labels[i])));
    if (last) svg.append(s('text', {class: 'th-val', x: X + bw / 2, y: Y - 5, 'text-anchor': 'middle'}, String(x)));
  });
  return svg;
}
function rowBars(rows){
  const mx = Math.max(1, ...rows.map(r => r.n || 0));
  return h('div', {class: 'th-load'}, rows.map(r => h('div', {class: 'th-row'}, h('span', {}, r.label),
    h('div', {class: 'trk'}, fill('fill ' + r.cls, pct(r.n || 0, mx))), h('span', {class: 'th-n num'}, r.n == null ? 'n/a' : r.n))));
}
function tickBar(label, st, max){
  if (!st || st.median == null) return h('div', {class: 'tk-row'}, h('span', {}, label), h('span', {class: 'muted'}, 'n/a'));
  const m = fmtH(st.median), p = fmtH(st.p90);
  const tick = h('span', {class: 'tk-tick'}); tick.style.left = pct(st.p90, max) + '%';
  return h('div', {class: 'tk-row'}, h('span', {}, label),
    h('div', {class: 'trk', role: 'img', 'aria-label': label + ': median ' + m.join('') + ', p90 ' + p.join('')}, fill('fill', pct(st.median, max)), tick),
    h('span', {class: 'tk-n num'}, h('b', {}, m[0] + m[1].split(' ')[0]), ' p90 ' + p[0] + p[1].split(' ')[0]));
}
const STACK_COLORS = ['var(--chart-1)', 'var(--chart-2)', 'var(--prog)', 'var(--chart-grid)'];
function stackBar(byGroup){
  const entries = Object.entries(byGroup || {}).filter(e => e[1] > 0).sort((a, b) => (a[0] === 'other') - (b[0] === 'other') || b[1] - a[1]);
  const total = entries.reduce((a, e) => a + e[1], 0) || 1;
  const color = i => STACK_COLORS[Math.min(i, STACK_COLORS.length - 1)];
  return h('div', {}, h('div', {class: 'sk-bar', role: 'img', 'aria-label': entries.map(e => e[0] + ' ' + e[1]).join(', ')},
    entries.map((e, i) => { const x = h('span', {'data-tip': e[0] + ': ' + e[1]}); x.style.flex = e[1]; x.style.background = color(i); return x; })),
    h('div', {class: 'legend'}, entries.map((e, i) => { const sw = h('i', {class: 'sk-sw'}); sw.style.background = color(i); return h('span', {}, sw, e[0], h('b', {}, e[1]), Math.round(100 * e[1] / total) + '%'); })));
}
function flowBar(stages){
  const total = stages.reduce((a, x) => a + x.n, 0);
  const col = {draft: 'var(--chart-grid)', review: 'var(--chart-2)', approved: 'var(--chart-1)', merged: 'var(--muted)'};
  return h('div', {class: 'pl-flow', 'aria-hidden': 'true'}, total ? stages.filter(x => x.n).map(x => { const e = h('span', {'data-tip': x.label + ': ' + x.n}); e.style.flex = x.n; e.style.background = col[x.key]; return e; }) : null);
}
function agingBar(w, comp, scale){
  comp = comp || {};
  const late = comp.late, nd = days(w.nudge_due), word = comp.days == null ? 'no start date' : comp.days + 'd';
  const label = late ? word + ', nudge ' + (-nd) + 'd late' : comp.due_today ? word + ', nudge today' : word;
  const bar = h('div', {class: 'trk', role: 'img', 'aria-label': 'Waiting ' + label}, fill('fill' + (late ? ' is-late' : ''), comp.days == null ? 0 : pct(comp.days, scale)));
  if (comp.nudge_at != null) { const t = h('span', {class: 'ag-tick', title: 'Nudge on ' + w.nudge_due}); t.style.left = pct(comp.nudge_at, scale) + '%'; bar.append(t); }
  return h('div', {class: 'ag-row'}, h('span', {class: 'ag-what'}, safe(w.link) ? [xa(w.link, {}, txt(w, 'what', true)), mentionIcons(w.what_parts)] : txt(w, 'what')),
    bar, h('span', {class: 'ag-l' + (late ? ' is-late' : '')}, label));
}
function jobBar(j){
  const eta = j.eta ? md(j.eta) : null;
  const line = j.finished ? 'done' : meta([j.total != null ? fmtN(j.done) + ' of ' + fmtN(j.total) + (j.unit ? ' ' + j.unit : '') : null,
    j.per_day ? fmtN(j.per_day) + ' a day' : null]);
  return h('div', {class: 'jb-row'}, h('div', {class: 'jb-top'}, h('b', {}, txt(j, 'label')), h('span', {class: 'num'}, j.pct == null ? '' : j.pct + '%')),
    h('div', {class: 'trk'}, fill('fill', j.finished ? 100 : (j.pct || 0))),
    h('div', {class: 'jb-sub'}, line, !j.finished && eta ? h('span', {class: j.late ? 'is-late' : ''}, (line.length ? ' · ' : '') + (j.late ? 'ETA passed (' + eta + ')' : 'ETA ' + eta)) : null,
      j.stale ? chip('not updated for ' + Math.max(0, -days((j.updated || '').slice(0, 10))) + ' days', 'is-gray') : null));
}
function fmtN(n){ return n == null ? '' : Number(n).toLocaleString('en-US'); }
// Hours: under 1h in minutes, under 10h one decimal, under 48h whole hours, else days with one decimal.
function fmtH(hrs){
  if (hrs == null) return ['n/a', ''];
  if (hrs < 1) return [String(Math.round(hrs * 60)), 'm median'];
  if (hrs < 10) return [hrs.toFixed(1), 'h median'];
  if (hrs < 48) return [String(Math.round(hrs)), 'h median'];
  return [(hrs / 24).toFixed(1), 'd median'];
}

// ---------- stats choice (shared by home and #stats) ----------
function choice(){
  let c = {group: 'me', win: '30'};
  try { const raw = store('ps-stats'); if (raw) c = Object.assign(c, JSON.parse(raw)); } catch (e) { /* defaults */ }
  if (!GROUPS[c.group]) c.group = 'me';
  if (c.win !== '30' && c.win !== '90') c.win = '30';
  return c;
}
function setChoice(c){ store('ps-stats', JSON.stringify({group: c.group, win: c.win})); }
const groupName = g => g === 'team' ? 'Team' : 'Me';
const TEAM_HINT = 'Set stats.team_slug or stats.team_members';

// ---------- header row ----------
function header(name, opts){
  opts = opts || {};
  const at = D.built_at || D.as_of, hrs = at ? (Date.now() - Date.parse(at)) / 36e5 : 0;
  const asof = at ? h('span', {class: 'hd-asof'}, 'as of ' + (clock(at) || at), hrs > 2 ? h('span', {class: 'hd-old'}, 'old snapshot, built ' + (hrs < 48 ? Math.floor(hrs) + 'h' : Math.floor(hrs / 24) + 'd') + ' ago') : null) : null;
  const fb = h('button', {type: 'button', class: 'hd-focus', id: 'focus-btn', 'aria-pressed': document.body.classList.contains('focus') ? 'true' : 'false', title: 'Focus: show only today and the top of the inbox (key f)'}, 'Focus');
  fb.addEventListener('click', () => setFocus(!document.body.classList.contains('focus'), true));
  return h('div', {class: 'hd'}, h('h1', {}, name, ' ', asof), h('div', {class: 'hd-r'}, opts.toggles || null, fb));
}
function statToggles(c, asLinks, onchange){
  if (!HAS_STATS) return null;
  const noTeam = !GROUPS.team;
  const mk = (g, w) => asLinks ? {href: '#stats/' + g + '/' + w} : {onclick: () => { const n = {group: g, win: w}; setChoice(n); onchange(n); }};
  return h('div', {class: 'hd-tg'},
    segmented('Whose numbers', [Object.assign({label: 'Me', on: c.group === 'me'}, mk('me', c.win)),
      Object.assign({label: 'Team', on: c.group === 'team', disabled: noTeam, title: noTeam ? TEAM_HINT : null}, mk('team', c.win))]),
    segmented('Time range', [Object.assign({label: '30d', on: c.win === '30'}, mk(c.group, '30')), Object.assign({label: '90d', on: c.win === '90'}, mk(c.group, '90'))]));
}

// ---------- today strip ----------
function inLabel(at){ const m = Math.round((Date.parse(at) - Date.now()) / 6e4); if (!(m > 0)) return null; return 'in ' + (m >= 60 ? Math.floor(m / 60) + 'h ' : '') + (m % 60) + 'm'; }
function stripBlock(){
  const late = STRIP.late || 0, done = STRIP.done_today || 0, nm = STRIP.next_meeting;
  const future = nm && !(Date.parse(nm.at) < Date.now());
  const cell = (n, label, cls, attrs) => h('a', Object.assign({class: 'td-c' + (cls ? ' ' + cls : ''), href: '#inbox'}, attrs || {}), h('b', {class: 'num'}, n), h('small', {}, label));
  return h('div', {class: 'td', role: 'group', 'aria-label': 'Today'},
    cell(STRIP.need_you || 0, 'need you'), cell(STRIP.due_today || 0, 'due today'), cell(late, 'late', late > 0 ? 'is-late' : ''),
    cell(done, 'done today', '', {title: 'Cleared from your inbox today', 'aria-label': done + ' cleared from your inbox today'}),
    h('div', {class: 'td-c td-meet'}, future ? [h('b', {class: 'num'}, nm.time), h('span', {class: 'td-w'}, nm.title), inLabel(nm.at) ? h('span', {class: 'td-in'}, inLabel(nm.at)) : null] : h('small', {}, 'No more meetings today')));
}

// ---------- inbox rows ----------
let SEEN = null;
function rowHref(it){ return safe(it.link) ? safe(it.link) : it.project_id && byId(it.project_id) ? '#p-' + it.project_id : '#inbox/' + it.hid; }
function inboxRow(it, hl){
  const ext = !!safe(it.link), n = days(it.due);
  const chips = [chip(it.effort, 'num')];
  if (it.late) chips.push(chip((-n) + 'd late', 'is-late'));
  else if (it.due_today) chips.push(chip('due today', 'is-due'));
  else if (it.due) chips.push(chip('due ' + when(it.due)));
  else if (it.age) chips.push(chip(it.age, 'age', {title: 'On your list since ' + (it.since || '').slice(0, 10)}));
  if (it.stale) chips.push(chip('stale', 'is-gray', {title: 'No due date and older than a week'}));
  if (it.who_waits) chips.push(chip(it.who_waits, 'who', {title: it.who_waits + ' is waiting'}));
  const isNew = SEEN && !SEEN.has(it.hid);
  return h('div', {class: 'irow' + (hl ? ' hl' : ''), id: 'i-' + it.hid, 'data-hid': it.hid},
    h('span', {class: 'idot' + (it.late ? ' is-late' : it.due_today ? ' is-due' : ''), role: 'img', 'aria-label': it.late ? 'late' : it.due_today ? 'due today' : 'open'}),
    h('span', {class: 'it'}, isNew ? h('span', {class: 'newdot', role: 'img', 'aria-label': 'new'}) : null,
      h('a', {class: 'rl', href: rowHref(it), target: ext ? '_blank' : null, rel: ext ? 'noopener' : null, title: it.why ? it.title + ' - ' + it.why : it.title}, txt(it, 'title', true)),
      mentionIcons(it.title_parts)),
    h('span', {class: 'im'}, chips));
}
function bandList(items, hl){
  const out = []; let band = null;
  items.forEach(it => { if (it.band !== band) { band = it.band; out.push(h('div', {class: 'band'}, (I.bands || {})[band] || '')); } out.push(inboxRow(it, it.hid === hl)); });
  return out;
}
function totals(){ return plural(I.open || 0, 'item') + (I.open ? ', about ' + I.effort : ''); }
function effortBar(shown, rest){
  const restMin = rest.reduce((a, i) => a + (i.effort_min || 0), 0);
  if (!shown.length) return null;
  return h('div', {class: 'eff', 'aria-hidden': 'true'}, shown.map(i => { const e = h('span', {class: i.late ? 'is-late' : ''}); e.style.flex = Math.max(1, i.effort_min || 1); return e; }),
    restMin ? (() => { const e = h('span', {class: 'o'}); e.style.flex = restMin; return e; })() : null);
}
function needsPanel(){
  const shown = ITEMS.slice(0, HOME_N), rest = ITEMS.slice(HOME_N), done = (I.done_today || []).length;
  return tile('Needs you', h('span', {class: 'tile-m num'}, totals()), effortBar(shown, rest),
    ITEMS.length ? h('div', {class: 'ilist'}, shown.map(it => inboxRow(it, false))) : h('div', {class: 'empty'}, 'Nothing needs you right now.'),
    h('div', {class: 'tile-f'}, rest.length ? h('a', {href: '#inbox'}, rest.length + ' more') : h('span'), h('span', {}, done + ' done today')));
}

// ---------- home tiles ----------
function kpiTiles(c){
  const g = GROUPS[c.group] || {}, wk = g.weekly || {}, w = (g.windows || {})[c.win] || {};
  const k = (label, val, unit, series) => h('div', {class: 'kp'}, h('span', {class: 'kp-l'}, label),
    h('span', {class: 'kp-v num' + (val === 'n/a' ? ' muted' : '')}, val, unit ? h('em', {}, unit) : null), spark(series));
  const f = fmtH((w.ttfr_h || {}).median), m = fmtH((w.ttm_h || {}).median);
  return h('div', {class: 'kp-row'}, k('PRs merged', w.merged == null ? 'n/a' : w.merged, '', wk.merged), k('Reviews given', w.reviews_given == null ? 'n/a' : w.reviews_given, '', wk.given),
    k('Time to first review', f[0], f[1], wk.ttfr_h), k('Time to merge', m[0], m[1], wk.ttm_h));
}
function thruTile(c){
  const g = GROUPS[c.group] || {}, wk = g.weekly || {}, w = (g.windows || {})[c.win] || {};
  const vals = wk.merged || [], labels = wk.weeks || [];
  const given = w.reviews_given || 0, recv = w.reviews_received || 0;
  return tile('Throughput', groupName(c.group) + ', last ' + c.win + ' days',
    h('div', {class: 'th-grid2'},
      h('div', {}, h('p', {class: 'th-sub'}, 'PRs merged per week, last ' + vals.length + ' weeks'),
        chart('weekly', colBars, {values: vals, labels, aria: 'PRs merged per week: ' + vals.join(', ')}),
        h('details', {class: 'th-tbl'}, h('summary', {}, 'Show as table'), h('div', {class: 'th-x'}, h('table', {},
          h('tr', {}, h('th', {}, 'Week of'), labels.map(l => h('th', {}, md(l)))), h('tr', {}, h('td', {}, 'Merged'), vals.map(v => h('td', {}, v))))))),
      h('div', {}, h('p', {class: 'th-sub'}, 'Review load'),
        rowBars([{label: 'Given', n: given, cls: 'is-c1'}, {label: 'Received', n: recv, cls: 'is-c2'}]),
        recv > 0 ? h('div', {class: 'th-ratio'}, h('b', {class: 'num'}, (given / recv).toFixed(1) + 'x'), ' given for each received') : null)));
}
function projStatus(p){
  if (isLate(p.deadline)) return {k: 'late', word: p.status || 'Late'};
  return {k: statusKey(p.status), word: p.status || 'Not started'};
}
function projRow(p){
  const j = (JOBS[p.id] || []).find(x => !x.finished);
  const sub = meta([p.epic ? txt(p, 'epic', true) : p.priority, j ? j.label + ' ' + (j.pct == null ? '' : j.pct + '%') + (j.eta ? ', ETA ' + j.eta.slice(5) : '') : null]);
  const st = projStatus(p), n = days(p.deadline), pc = Math.max(0, Math.min(100, p.progress_pct || 0));
  return h('div', {class: 'pj'},
    h('div', {class: 'pj-name'}, h('a', {class: 'rl', href: '#p-' + p.id}, p.name), mentionIcons(p.epic_parts), badge(inboxOf(p.id).length), sub.length ? h('small', {}, sub) : null),
    h('div', {class: 'pj-bar'}, h('div', {class: 'trk', role: 'img', 'aria-label': pc + ' percent done'}, fill('fill', pc)), h('span', {class: 'pj-pct num'}, pc + '%')),
    h('div', {class: 'pj-st'}, h('span', {class: 'dot ' + st.k, 'aria-hidden': 'true'}), st.word),
    h('div', {class: 'pj-dl'}, p.deadline ? (n < 0 ? h('span', {class: 'is-late'}, (-n) + 'd late') : [h('b', {}, md(p.deadline)), ' ', h('span', {class: 'num'}, n + 'd')]) : null));
}
function projectsTile(list, title){
  return tile(title || 'Projects', list.length + ' active', h('div', {class: 'pj-list'}, list.map(projRow)));
}
const MARK = {deadline: 'Deadline', milestone: 'Milestone', ask: 'Ask', job: 'Job done'};
function marker(kind, x, y, cls){
  const c = 'tl-mk ' + kind + (cls ? ' ' + cls : '');
  if (kind === 'deadline') return s('path', {class: c, d: `M${x},${y - 7}L${x + 7},${y}L${x},${y + 7}L${x - 7},${y}Z`});
  if (kind === 'milestone') return s('circle', {class: c, cx: x, cy: y, r: 5.5});
  if (kind === 'job') return s('rect', {class: c, x: x - 5, y: y - 5, width: 10, height: 10, rx: 1.5});
  return s('circle', {class: c, cx: x, cy: y, r: 3.5});
}
function timelineSvg(tl, W){
  const n = tl.days || 21, pl = 10, pr = 16, rowH = 44, top = 18, cw = 6.4;
  const x = d => pl + d / (n - 1) * (W - pl - pr);
  const rows = [[], [], []], placed = [];
  let dropped = 0;
  (tl.events || []).forEach(e => {
    const X = x(e.day), wd = Math.max(e.label.length, (e.sub || '').length) * cw + 18;
    if (X + wd > W + 4 && X - wd < 0) { dropped++; return; }
    // A label near the right edge flips to the left of its marker, so the row test uses the label's real left edge.
    const flip = X + wd > W, left = flip ? X - wd : X - 8, right = flip ? X + 8 : X + wd;
    const r = rows.findIndex(row => !row.length || row[row.length - 1] < left - 4);
    if (r < 0) { dropped++; return; }
    rows[r].push(right); placed.push({e, X, r, flip});
  });
  const used = Math.max(1, rows.filter(r => r.length).length), axisY = top + used * rowH + 4, H = axisY + 24;
  const svg = s('svg', {class: 'tl-svg', viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', 'aria-label': 'Dates in the next ' + n + ' days'});
  svg.append(s('line', {class: 'tl-axis', x1: pl, x2: W - pr, y1: axisY, y2: axisY}));
  for (let d = 0; d < n; d++) {
    const dt = addDays(today, d);
    if (d === 0 || new Date(Date.parse(dt)).getUTCDay() === 1) {
      svg.append(s('line', {class: 'tl-tick', x1: x(d), x2: x(d), y1: axisY - 4, y2: axisY + 4}),
        s('text', {class: 'tl-day', x: x(d), y: axisY + 17, 'text-anchor': d === 0 ? 'start' : 'middle'}, md(dt)));
    }
  }
  svg.append(s('line', {class: 'tl-now', x1: x(0), x2: x(0), y1: 2, y2: axisY}), s('text', {class: 'tl-nowl', x: x(0) + 5, y: 11}, 'Today'));
  placed.forEach(({e, X, r, flip}) => {
    const y = top + r * rowH + 6, lx = flip ? X - 10 : X + 10, anchor = flip ? 'end' : 'start';
    const dl = e.late ? (-days(e.date)) + ' days late' : e.day === 0 ? 'today' : 'in ' + e.day + ' days';
    const href = safe(e.link) || (byId(e.project_id) ? '#p-' + e.project_id : null);
    const g = s('g', {class: 'tl-ev'}, s('title', {}, e.label + ', ' + e.sub + ', ' + md(e.date) + ' (' + dl + ')'));
    g.append(marker(e.kind, X, y, (e.late ? 'is-late' : '') + (e.soon ? ' is-soon' : '')));
    const lab = s('text', {class: 'tl-lb', x: lx, y: y + 4, 'text-anchor': anchor}, e.label);
    const sub = s('text', {class: 'tl-sub', x: lx, y: y + 18, 'text-anchor': anchor}, e.sub || '');
    if (href) { const a = s('a', {href}); if (safe(e.link)) { a.setAttribute('target', '_blank'); a.setAttribute('rel', 'noopener'); } a.append(lab, sub); g.append(a); } else g.append(lab, sub);
    g.append(s('circle', {class: 'tl-ad' + (e.late ? ' is-late' : ''), cx: X, cy: axisY, r: 4}));
    svg.append(g);
  });
  const more = (tl.more || 0) + dropped;
  if (more) svg.append(s('text', {class: 'tl-more', x: W - pr, y: 11, 'text-anchor': 'end'}, '+' + more + ' more'));
  return svg;
}
function timelineTile(tl, title){
  const kinds = [...new Set((tl.events || []).map(e => e.kind))];
  const body = (tl.events || []).length ? [chart('timeline', timelineSvg, tl),
    h('div', {class: 'legend'}, ['deadline', 'milestone', 'ask', 'job'].filter(k => kinds.includes(k)).map(k => h('span', {}, s('svg', {width: 16, height: 16, viewBox: '0 0 16 16', 'aria-hidden': 'true'}, marker(k, 8, 8)), MARK[k]))),
  ] : h('div', {class: 'empty'}, 'No dates in the next 3 weeks.');
  return tile(title || 'Next 3 weeks', md(tl.from) + ' to ' + md(tl.to), body);
}
function pill(p, stageKey){
  const cls = {draft: 'draft', review: 'rev', approved: 'ok', merged: 'done'}[stageKey];
  const flags = [p.ci_failed ? 'CI failed' : null, p.conflict ? 'conflict' : null].filter(Boolean);
  const title = p.title + (flags.length ? ' (' + flags.join(', ') + ')' : '');
  return xa(p.url, {class: 'pl-pill ' + cls, title, 'aria-label': p.label + ': ' + title}, p.label, flags.length ? icon('M6.4 5 12 10.6 17.6 5 19 6.4 13.4 12 19 17.6 17.6 19 12 13.4 6.4 19 5 17.6 10.6 12 5 6.4z', 10) : null);
}
function pipelinePanel(all){
  if (!PIPE) return null;
  const owed = PIPE.reviews_owed || 0, any = PIPE.stages.some(x => x.n);
  return tile('PR pipeline', owed ? h('a', {class: 'chip is-owed num', href: '#inbox'}, plural(owed, 'review') + ' owed') : null,
    any ? [flowBar(PIPE.stages), PIPE.stages.map(st => {
      const pills = all ? st.pills : st.pills.slice(0, PILLS_PER_STAGE), extra = st.pills.length - pills.length;
      return h('div', {class: 'pl-stage'}, h('span', {class: 'pl-sn'}, st.label), h('span', {class: 'pl-sc num'}, st.n),
        h('span', {class: 'pl-pills'}, pills.map(p => pill(p, st.key)), extra > 0 ? h('a', {class: 'pl-more', href: '#prs'}, '+' + extra) : null));
    })] : h('div', {class: 'empty'}, 'No open PRs.'));
}
function waitingPanel(){
  const idx = W.map((w, i) => i).sort((a, b) => ((WV.rows[b] || {}).late - (WV.rows[a] || {}).late) || (((WV.rows[b] || {}).days || 0) - ((WV.rows[a] || {}).days || 0)));
  const late = WV.rows.filter(r => r.late).length, due = WV.rows.filter(r => r.late || r.due_today).length;
  const people = new Set(W.map(w => w.person)).size;
  return tile('Waiting on', late ? h('span', {class: 'tile-m is-late'}, plural(late, 'nudge') + ' late') : plural(due, 'nudge') + ' due',
    h('a', {class: 'wt-big', href: '#waiting'}, h('b', {class: 'num'}, people), people === 1 ? 'person' : 'people'),
    h('ul', {class: 'wt-list'}, idx.slice(0, 4).map(i => { const w = W[i], r = WV.rows[i] || {};
      const what = safe(w.link) ? [xa(w.link, {class: 'chip', title: w.what || ''}, txt(w, 'what', true)), mentionIcons(w.what_parts)] : chip(txt(w, 'what'), '', {title: w.what || ''});
      return h('li', {}, h('span', {}, w.person), r.late ? chip('nudge ' + (-days(w.nudge_due)) + 'd late', 'is-late') : h('span', {class: 'wt-what'}, what)); })),
    W.length > 4 ? h('div', {class: 'tile-f'}, h('a', {href: '#waiting'}, (W.length - 4) + ' more'), h('span')) : null);
}

function region(name, ...kids){ return h('section', {class: 'region', 'data-region': name}, kids); }
function homePage(){
  const c = choice();
  const kp = region('kpis'), th = region('thru');
  const fillStats = cc => { if (!HAS_STATS) return; kp.replaceChildren(kpiTiles(cc)); th.replaceChildren(thruTile(cc));
    const tg = document.querySelector('.hd-tg'); if (tg) tg.replaceWith(statToggles(cc, false, fillStats)); drawCharts(true); };
  if (HAS_STATS) { kp.append(kpiTiles(c)); th.append(thruTile(c)); }
  const main = h('div', {class: 'home-main'}, HAS_STATS ? th : null, P.length ? region('projects', projectsTile(P)) : null, region('timeline', timelineTile(TL)));
  const side = h('div', {class: 'home-side'}, region('inbox', needsPanel()), PIPE ? region('pipeline', pipelinePanel(false)) : null, W.length ? region('waiting', waitingPanel()) : null);
  return [h('div', {class: 'home'}, region('head', header(weekday(today) + ', ' + md(today), {toggles: statToggles(c, false, fillStats)})), region('today', stripBlock()),
    HAS_STATS ? kp : null, main, side)];
}

// ---------- inbox page ----------
function inboxPage(hl){
  const shown = ITEMS.slice(0, CAP), rest = ITEMS.slice(CAP), sn = I.snoozed || [], done = I.done_today || [];
  const restOpen = !!hl && rest.some(i => i.hid === hl);
  return [header('Inbox'), tile('Needs you', h('span', {class: 'tile-m num'}, totals()), effortBar(ITEMS, []),
    ITEMS.length ? h('div', {class: 'ilist'}, bandList(shown, hl)) : h('div', {class: 'empty'}, 'Nothing needs you right now.'),
    rest.length ? h('details', {class: 'fold', open: restOpen ? '' : null}, h('summary', {}, rest.length + ' more'), h('div', {class: 'ilist'}, bandList(rest, hl))) : null,
    sn.length ? h('details', {class: 'fold'}, h('summary', {}, sn.length + ' snoozed'), h('div', {class: 'ilist'}, sn.map(it => {
      const r = inboxRow(it, it.hid === hl); r.querySelector('.im').prepend(chip('until ' + it.snooze_until)); return r; }))) : null,
    done.length ? h('details', {class: 'fold'}, h('summary', {}, done.length + ' done today'), h('ul', {class: 'plain', style: 'padding:6px 0 4px'},
      done.map(d => h('li', {}, d.title, h('span', {class: 'd'}, 'Cleared ' + clock(d.at)))))) : null)];
}

// ---------- projects, PRs, stats, delivered ----------
function projectsPage(){ return [header('Projects'), P.length ? projectsTile(P, 'All projects') : tile('Projects', null, h('div', {class: 'empty'}, 'No projects yet.')), O.length ? otherBody() : null]; }
function prsPage(){
  const rq = ((D.feeds || {}).github || {}).review_requests || [];
  return [header('PRs'), pipelinePanel(true), tile('Reviews asked of you', plural(rq.length, 'request'), rq.length ? h('div', {class: 'rq-list'}, rq.map(r =>
    h('div', {class: 'rq'}, xa(r.url, {class: 'rq-t'}, r.title || r.url), h('span', {class: 'rq-m'}, meta([r.author, ((r.additions || 0) + (r.deletions || 0)) + ' lines', r.requested_at ? 'asked ' + (Math.max(0, -days(r.requested_at.slice(0, 10))) || 'today') + (days(r.requested_at.slice(0, 10)) < 0 ? 'd ago' : '') : null]))))) : h('div', {class: 'empty'}, 'No reviews waiting on you.'))];
}
function statsPage(c){
  const base = [header('Stats', {toggles: statToggles(c, true)})];
  if (!HAS_STATS) return base.concat(tile('Stats', null, h('div', {class: 'empty'}, 'Stats are not ready: ' + ((ST && ST.error) || 'no data') + '. Run eng-stats doctor.')));
  const w = ((GROUPS[c.group] || {}).windows || {})[c.win] || {};
  const note = ST.ok === false ? h('div', {class: 'note'}, 'Stats did not refresh: ' + (ST.error || 'unknown error') + ' (data to ' + ((ST.coverage || {}).to || '?') + ')') : null;
  const fr = w.ttfr_h || {}, mg = w.ttm_h || {}, max = Math.max(fr.p90 || 0, mg.p90 || 0) * 1.1 || 1;
  const turn = (w.merged || 0) < 5 ? h('div', {class: 'empty'}, 'Too few merged PRs in this window to show turnaround.')
    : [tickBar('First review', fr, max), tickBar('Merge', mg, max), h('p', {class: 'muted small'}, plural(w.merged_no_review || 0, 'PR') + ' merged with no review, ' + plural(w.re_reviews || 0, 're-review'))];
  const groups = w.by_repo_group || {}, onlyOther = Object.keys(groups).filter(k => groups[k] > 0).every(k => k === 'other');
  const cov = ST.coverage || {}, org = ST.org || C.github_org;
  const q = org && cov.from && cov.to ? 'https://github.com/search?type=pullrequests&q=' + encodeURIComponent('org:' + org + ' is:pr updated:' + cov.from + '..' + cov.to) : null;
  return base.concat(note, region('kpis', kpiTiles(c)), thruTile(c), h('div', {class: 'two'}, tile('Turnaround', groupName(c.group) + ', last ' + c.win + ' days', turn),
    onlyOther ? null : tile('By repo group', plural(w.merged || 0, 'PR') + ' merged', stackBar(groups))),
    h('p', {class: 'muted small'}, 'Excluded: ' + plural((ST.excluded || {}).bot_prs || 0, 'bot PR') + '. Lines of code: off. ',
      q ? xa(q, {}, 'Data from ' + cov.from + ' to ' + cov.to) : 'Data from ' + (cov.from || '?') + ' to ' + (cov.to || '?'), '.',
      cov.truncated_windows > 0 ? " Some busy hours hit GitHub's search cap; counts may be a little low." : null));
}
function deliveredPage(){
  return [header('Delivered, not confirmed'), tile('Delivered, not confirmed', plural(DLV.length, 'delivery'), h('div', {class: 'dv-list'}, DLV.map(d =>
    h('div', {class: 'dv'}, h('span', {class: 'dv-t'}, safe(d.link) ? xa(d.link, {}, d.title_parts ? parts(d.title_parts, true) : d.title) : (d.title_parts ? parts(d.title_parts, false) : d.title)),
      h('div', {class: 'trk', role: 'img', 'aria-label': d.elapsed + ' of ' + d.total + ' days'}, fill('fill is-c2', pct(d.elapsed, d.total))),
      h('span', {class: 'dv-l' + (d.late ? ' is-late' : '')}, d.late ? plural(-d.left, 'day') + ' late' : d.left === 0 ? 'due today' : plural(d.left, 'day') + ' left')))))];
}

// ---------- project page (sections are separate so later visuals can slot in) ----------
function heroCard(p){
  const items = allItems(p), t = tally(items), n = inboxOf(p.id).length;
  return h('section', {class: 'tile'}, h('div', {class: 'hero'}, ring(p.progress_pct, 92),
    h('div', {class: 't'}, h('div', {class: 'nm'}, h('h2', {class: 'hero-n'}, p.name), badge(n)),
      h('div', {class: 'chips'}, statusChip(p.status), p.priority ? chip(p.priority) : null, p.epic ? h('span', {class: 'chip'}, refNode(p.epic, p.epic_parts)) : null, dueChip(p.deadline, 'Deadline')))),
    items.length ? h('div', {style: 'margin-top:18px'}, sbar(t), legend(t)) : null);
}
function jobsCard(p){ const js = JOBS[p.id] || []; return js.length ? tile('Long jobs', plural(js.length, 'job'), js.map(jobBar)) : null; }
function needsCard(p){
  const needs = p.needs_me || [], extra = inboxOf(p.id).filter(i => !i.from_needs_me);
  const body = [];
  if (needs.length) body.push(h('ul', {class: 'needs'}, needs.map(n => h('li', {},
    h('span', {class: 'dot ' + (isLate(n.due) ? 'late' : 'none'), role: 'img', 'aria-label': isLate(n.due) ? 'late' : 'open'}),
    h('span', {class: 'ask'}, safe(n.link) ? [xa(n.link, {}, txt(n, 'ask', true)), mentionIcons(n.ask_parts)] : txt(n, 'ask'),
      h('span', {class: 'sub' + (isLate(n.due) ? ' is-late' : '')}, meta([refNode(n.ticket, n.ticket_parts), n.why ? txt(n, 'why') : null, n.due ? 'due ' + n.due + (when(n.due) ? ' (' + when(n.due) + ')' : '') : null])))))));
  if (extra.length) body.push(h('div', {class: 'ilist', style: needs.length ? 'margin-top:10px' : ''}, extra.map(it => inboxRow(it, false))));
  return tile('Needed from you', null, body.length ? body : h('span', {class: 'empty'}, 'Nothing right now. This one is moving without you.'));
}
function standsCard(p){
  if (!p.summary && !p.next_milestone && !p.progress_basis) return null;
  return tile('Where it stands', null, p.summary ? h('p', {class: 'sum'}, txt(p, 'summary')) : null,
    p.next_milestone ? h('p', {class: 'sum', style: 'margin-top:10px;color:var(--strong)'}, 'Next: ', txt(p, 'next_milestone'), p.next_milestone_date ? ' (' + md(p.next_milestone_date) + ')' : null) : null,
    p.progress_basis ? h('details', {class: 'fold basis-fold'}, h('summary', {}, 'How the percent was worked out'), h('div', {class: 'basis'}, (p.progress_pct || 0) + '%: ' + p.progress_basis)) : null);
}
function breakdownCard(p){
  const groups = p.breakdown || [];
  if (!groups.length) return null;
  return tile('Full breakdown', h('button', {type: 'button', id: 'toggle-all', class: 'tool'}, 'Open all'),
    groups.map(g => { const gi = g.items || [], gt = tally(gi); return h('details', {class: 'grp'}, h('summary', {}, h('span', {class: 'g'}, g.group), sbar(gt), h('span', {class: 'ct'}, gt.done + ' of ' + gi.length + ' done')),
      gi.map(i => h('div', {class: 'item' + (key(i.state) === 'done' ? ' is-done' : '')}, h('span', {class: 'dot ' + key(i.state), title: LABEL[key(i.state)]}), h('span', {class: 'tx'}, txt(i, 'text')),
        h('span', {class: 'mt'}, meta([LABEL[key(i.state)], i.owner, refNode(i.ref, i.ref_parts), i.date]))))); }));
}
function waitsCard(p){
  const idx = W.map((w, i) => i).filter(i => W[i].project_id === p.id);
  return idx.length ? tile('Waiting on others', null, idx.map(i => h('div', {class: 'ag-person'}, h('b', {}, W[i].person), agingBar(W[i], WV.rows[i], WV.scale_days)))) : null;
}
function notesCards(p){
  const dec = p.decisions || [], rec = p.recent_progress || [];
  if (!dec.length && !rec.length) return null;
  return h('div', {class: 'two'},
    dec.length ? tile('Recent decisions', null, h('ul', {class: 'plain'}, dec.map(d => h('li', {}, h('span', {class: 'd'}, d.date || ''), txt(d, 'decision'))))) : null,
    rec.length ? tile('Recent progress', null, h('ul', {class: 'plain'}, rec.map(d => h('li', {}, h('span', {class: 'd'}, d.date || ''), txt(d, 'text'))))) : null);
}
function linksCard(p){ return (p.links || []).length ? tile('Links', null, h('div', {class: 'chips'}, p.links.map(l => safe(l.url) ? h('a', {class: 'chip', href: safe(l.url), target: '_blank', rel: 'noopener'}, l.label) : chip(l.label)))) : null; }
function projectPage(p){
  return [header(p.name), heroCard(p), jobsCard(p), PTL[p.id] ? timelineTile(PTL[p.id], 'Dates') : null, needsCard(p), standsCard(p), breakdownCard(p), waitsCard(p), notesCards(p), linksCard(p)];
}

// ---------- waiting and other items ----------
function waitingPage(){
  const by = {}; W.forEach((w, i) => (by[w.person] = by[w.person] || []).push(i));
  const names = Object.keys(by).sort((a, b) => by[b].length - by[a].length || a.localeCompare(b));
  const due = WV.rows.filter(r => r.late || r.due_today).length;
  return [header('Waiting on others'),
    h('div', {class: 'sum-row'}, h('span', {}, h('b', {class: 'num'}, names.length), names.length === 1 ? 'person' : 'people'), h('span', {}, h('b', {class: 'num'}, W.length), 'things you are waiting for'), h('span', {}, h('b', {class: 'num'}, due), 'nudges due')),
    W.length ? h('div', {class: 'two'}, names.map(n => tile(n, String(by[n].length), by[n].map(i => {
      const w = W[i], p = byId(w.project_id);
      return h('div', {class: 'ag-person'}, agingBar(w, WV.rows[i], WV.scale_days), h('span', {class: 'sub'}, meta([p ? h('a', {href: '#p-' + p.id}, p.name) : null, w.where ? txt(w, 'where') : null])));
    })))) : tile('Waiting on others', null, h('div', {class: 'empty'}, 'Nothing is waiting on anyone else.'))];
}
function otherBody(){
  const sorted = O.slice().sort((a, b) => (key(a.state) === 'done') - (key(b.state) === 'done') || (b.needs_me ? 1 : 0) - (a.needs_me ? 1 : 0));
  return tile('Other items', openOff.length + ' open, ' + offNeeds + ' need you', sbar(tally(O)), legend(tally(O)),
    h('div', {class: 'oo-list'}, sorted.map(o => h('div', {class: 'oo'},
      h('div', {class: 'oo-top'}, o.progress_pct != null ? ring(o.progress_pct, 40) : h('span', {class: 'dot ' + key(o.state)}), h('div', {class: 'oo-name' + (key(o.state) === 'done' ? ' muted' : '')}, txt(o, 'title')), o.needs_me && key(o.state) !== 'done' ? h('span', {class: 'badge'}, 'needs you') : null),
      h('div', {class: 'chips'}, chip([h('span', {class: 'dot ' + key(o.state)}), LABEL[key(o.state)]]), key(o.state) !== 'done' ? dueChip(o.due) : null, o.ref ? h('span', {class: 'chip'}, refNode(o.ref, o.ref_parts)) : null),
      o.note ? h('div', {class: 'small'}, txt(o, 'note')) : null))));
}
function otherPage(){ return [header('Other items'), otherBody()]; }

// ---------- shell: rail, sheet, focus, routes ----------
const ICONS = {
  home: 'M12 3 2.5 11h2.5v9h5.5v-6h3v6H19v-9h2.5z',
  inbox: 'M3 4h18v10h-5.5a3.5 3.5 0 0 1-7 0H3zm0 12h4.6a5.5 5.5 0 0 0 8.8 0H21v4H3z',
  projects: 'M2 5h8l2 2h10v13H2z',
  prs: 'M6 2a3 3 0 0 1 1 5.8v8.4A3 3 0 1 1 5 16.2V7.8A3 3 0 0 1 6 2zm12 14.2V9a2 2 0 0 0-2-2h-3v2L10 6l3-3v2h3a4 4 0 0 1 4 4v7.2a3 3 0 1 1-2 0z',
  stats: 'M3 20h18v2H3zM4 12h4v7H4zM10 6h4v13h-4zM16 9h4v10h-4z',
  more: 'M5 10a2 2 0 1 1 0 4 2 2 0 0 1 0-4zm7 0a2 2 0 1 1 0 4 2 2 0 0 1 0-4zm7 0a2 2 0 1 1 0 4 2 2 0 0 1 0-4z',
};
function navEntries(){
  return {
    rail: [{hash: 'home', label: 'Home', icon: 'home'}, {hash: 'inbox', label: 'Inbox', icon: 'inbox', count: I.open || 0}, {hash: 'projects', label: 'Projects', icon: 'projects'},
      PIPE ? {hash: 'prs', label: 'PRs', icon: 'prs'} : null, ST ? {hash: 'stats', label: 'Stats', icon: 'stats'} : null, {hash: 'more', label: 'More', icon: 'more'}].filter(Boolean),
    sheet: [{hash: 'waiting', label: 'Waiting on others', count: W.length}, DLV.length ? {hash: 'delivered', label: 'Delivered, not confirmed', count: DLV.length} : null,
      O.length ? {hash: 'other', label: 'Other items', count: offNeeds} : null].filter(Boolean).concat(P.map(p => ({hash: 'p-' + p.id, label: p.name, pct: p.progress_pct || 0, count: inboxOf(p.id).length}))),
  };
}
function setMenu(open){
  $('sheet').hidden = !open; $('scrim').hidden = !open;
  const more = $('more-btn'); if (more) more.setAttribute('aria-expanded', open ? 'true' : 'false');
  if (open) { const f = $('sheet').querySelector('a'); if (f) f.focus(); }
}
function setFocus(on, save){
  document.body.classList.toggle('focus', on);
  const b = $('focus-btn'); if (b) b.setAttribute('aria-pressed', on ? 'true' : 'false');
  if (save) store('ps-focus', on ? '1' : '0');
}
function buildNav(){
  const nav = navEntries(), rail = $('rail'), sheet = $('sheet');
  rail.append(h('div', {class: 'rl-mark', 'aria-hidden': 'true'}, (BASE_TITLE.trim()[0] || 'S').toUpperCase()));
  nav.rail.forEach(e => {
    const kids = [e.count ? h('span', {class: 'rl-badge num', 'aria-label': e.count + ' open'}, e.count) : null, icon(ICONS[e.icon], 22), h('span', {class: 'rl-l'}, e.label)];
    if (e.hash === 'more') { const b = h('button', {type: 'button', class: 'rl-i', id: 'more-btn', 'data-h': 'more', 'aria-expanded': 'false', 'aria-controls': 'sheet'}, kids); b.addEventListener('click', () => setMenu($('sheet').hidden)); rail.append(b); }
    else rail.append(h('a', {class: 'rl-i', href: '#' + e.hash, 'data-h': e.hash}, kids));
  });
  const close = h('button', {class: 'sh-close', type: 'button'}, 'Close');
  sheet.append(close, h('div', {class: 'sh-lbl'}, 'More'));
  nav.sheet.forEach((e, i) => {
    if (e.pct != null && (i === 0 || nav.sheet[i - 1].pct == null)) sheet.append(h('div', {class: 'sh-lbl'}, 'Projects'));
    sheet.append(h('a', {href: '#' + e.hash, 'data-h': e.hash}, e.pct != null ? ring(e.pct, 22) : null, h('span', {class: 'nm'}, e.label), e.pct != null ? h('span', {class: 'pc num'}, e.pct + '%') : null, badge(e.count)));
  });
  close.addEventListener('click', () => { setMenu(false); $('more-btn').focus(); });
  $('scrim').addEventListener('click', () => setMenu(false));
  sheet.addEventListener('click', e => { if (e.target.closest && e.target.closest('a')) setMenu(false); });
}
function railBase(r){
  if (r.p) return 'projects';
  if (['waiting', 'delivered', 'other'].includes(r.cur)) return 'more';
  return r.cur;
}
const OLD = {'': 'home', overview: 'home', people: 'waiting', oneoffs: 'other'};
function route(){
  let hash = (location.hash || '').slice(1);
  try { hash = decodeURIComponent(hash); } catch (e) { /* keep it raw */ }
  if (hash in OLD) hash = OLD[hash];
  if (hash.startsWith('p-') && byId(hash.slice(2))) return {cur: hash, p: byId(hash.slice(2))};
  if (hash === 'inbox') return {cur: 'inbox'};
  if (hash.startsWith('inbox/')) return {cur: 'inbox', hl: hash.slice(6)};
  if (hash === 'waiting') return {cur: 'waiting'};
  if (hash === 'projects') return {cur: 'projects'};
  if (hash === 'prs' && PIPE) return {cur: 'prs'};
  if (hash === 'delivered' && DLV.length) return {cur: 'delivered'};
  if (hash === 'other' && O.length) return {cur: 'other'};
  if ((hash === 'stats' || hash.startsWith('stats/')) && ST) {
    const bits = hash.split('/').slice(1);
    const c = choice();
    if (bits.length) {
      c.group = bits[0] === 'team' && GROUPS.team ? 'team' : 'me';
      c.win = bits[1] === '90' ? '90' : '30';
      setChoice(c);
    }
    return {cur: 'stats', c};
  }
  return {cur: 'home'};
}
function loadSeen(){
  try { const raw = localStorage.getItem('ps-seen'); return raw == null ? 'first' : new Set(JSON.parse(raw)); } catch (e) { return null; }
}
function saveSeen(prev){
  // Rows inside a closed fold were not seen, so they keep their dot until the fold is opened on a later visit.
  const drawn = [...document.querySelectorAll('#page [data-hid]')].filter(e => !e.closest('details:not([open])')).map(e => e.dataset.hid);
  if (!drawn.length && prev !== 'first') return;
  try {
    const old = prev instanceof Set ? [...prev] : [];
    const out = old.filter(x => !drawn.includes(x)).concat(drawn).slice(-500);
    localStorage.setItem('ps-seen', JSON.stringify(out));
  } catch (e) { /* no dots, nothing stored */ }
}
function show(){
  const r = route(), cur = r.cur;
  const tracksNew = cur === 'home' || cur === 'inbox';
  const prev = tracksNew ? loadSeen() : null;
  SEEN = prev instanceof Set ? prev : null;
  CHARTS = [];
  const body = r.p ? projectPage(r.p) : cur === 'inbox' ? inboxPage(r.hl) : cur === 'waiting' ? waitingPage() : cur === 'other' ? otherPage()
    : cur === 'projects' ? projectsPage() : cur === 'prs' ? prsPage() : cur === 'stats' ? statsPage(r.c) : cur === 'delivered' ? deliveredPage() : homePage();
  const foot = h('footer', {class: 'foot'}, sourcesLine(cur === 'inbox'), C.source_note ? h('span', {}, C.source_note) : null,
    UNL.length ? h('details', {class: 'unl'}, h('summary', {}, chip(plural(UNL.length, 'mention') + ' ' + (UNL.length === 1 ? 'has' : 'have') + ' no link', 'is-gray')),
      h('ul', {class: 'plain'}, UNL.map(u => h('li', {}, h('b', {}, u.text), ' ', h('span', {class: 'd'}, u.where + ' (' + u.why + ')'))))) : null,
    r.p ? h('span', {}, 'Percent done is an estimate; "How the percent was worked out" says how.') : null);
  $('page').replaceChildren(...body.flat().filter(Boolean), foot);
  document.body.dataset.page = cur === 'home' ? 'home' : 'other';
  const base = railBase(r);
  document.querySelectorAll('#rail .rl-i').forEach(a => a.dataset.h === base ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current'));
  document.querySelectorAll('#sheet a').forEach(a => a.dataset.h === cur ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current'));
  const first = document.querySelector('#page details.grp'); if (first) first.open = true;
  drawCharts(true);
  if (tracksNew && prev !== null) saveSeen(prev);
  const target = r.hl ? document.getElementById('i-' + r.hl) : null;
  if (target) target.scrollIntoView({block: 'center'}); else window.scrollTo(0, 0);
}
function sourcesLine(withMissing){
  const src = (D.sources || []).filter(x => withMissing || x.state !== 'missing');
  if (!src.length) return null;
  const word = {stale: 'stale', failing: 'failing', missing: 'not set up'};
  return h('div', {class: 'srcs'}, 'Sources', src.map(x => h('span', {class: 'src' + (x.state === 'ok' ? '' : ' bad'),
    title: x.state === 'failing' ? (x.error || 'failed') + (x.last_ok_at ? ' (last good ' + clock(x.last_ok_at) + ')' : '') : x.state === 'missing' ? 'Not set up on this machine' : x.state === 'stale' ? 'Not refreshed on schedule' : 'Up to date'},
    meta([x.label, x.as_of, word[x.state]]))));
}
function tooltip(){
  const tip = h('div', {class: 'tip', hidden: ''}); document.body.append(tip);
  document.addEventListener('pointermove', e => {
    const t = e.target.closest && e.target.closest('[data-tip]');
    if (!t) { tip.hidden = true; return; }
    tip.textContent = t.getAttribute('data-tip'); tip.hidden = false;
    tip.style.left = Math.max(8, Math.min(e.clientX + 12, innerWidth - tip.offsetWidth - 8)) + 'px'; tip.style.top = Math.max(8, e.clientY - 34) + 'px';
  });
}
function build(){
  document.title = (I.open > 0 ? '(' + I.open + ') ' : '') + BASE_TITLE;
  buildNav();
  tooltip();
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { if (!$('sheet').hidden) { setMenu(false); $('more-btn').focus(); } return; }
    const t = e.target, typing = t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable);
    if ((e.key === 'f' || e.key === 'F') && !typing && !e.metaKey && !e.ctrlKey && !e.altKey) setFocus(!document.body.classList.contains('focus'), true);
  });
  document.addEventListener('click', e => { if (e.target && e.target.id === 'toggle-all') { const ds = [...document.querySelectorAll('#page details.grp')], open = ds.some(d => !d.open); ds.forEach(d => d.open = open); e.target.textContent = open ? 'Close all' : 'Open all'; } });
  let timer = null;
  addEventListener('resize', () => { clearTimeout(timer); timer = setTimeout(() => drawCharts(false), 200); });
  setFocus(store('ps-focus') === '1', false);
  show();
}
addEventListener('hashchange', show);
build();
