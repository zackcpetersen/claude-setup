// Status page script. build.py inlines this file, page.css and the data into template.html.
// Pages (hash routes): home (empty hash), #need, #late, #running, #wins, #shelf (also #parked), #p-<id> (one project),
// #github (also #github-<me|team>-<30|90>). Older hashes (#inbox, #stats, #prs, #waiting...) map to the nearest page.
// Every number, label and grouping is worked out in derive.py (focus_view); this file only lays the data out.
// Building blocks: row() for every list row, list() for a capped list that grows in place, section() for a titled
// card, subpage() for a page with a way back. New pages add a renderer to ROUTES.
const D = JSON.parse(document.getElementById('data').textContent);
const C = D.config || {};
const P = D.projects || [], W = D.waiting_on || [];
const F = D.focus || {};
const CAP = F.cap ?? 5, UP_N = F.up_next_shown ?? 3;
const NEEDS = [F.hero, ...(F.up_next || [])].filter(Boolean);
const RUN = F.running || [], WINS = F.wins || [], SHELF = F.shelf || [], LATE = F.late_items || [];
const SM = F.shelf_meta || {loose: 0, cap: null, stale_days: 14, stale: 0};
const TILES = F.tiles || [];
const ST = D.stats || null, GROUPS = (ST && ST.groups) || {}, HAS_STATS = !!ST && Object.keys(GROUPS).length > 0;
const PIPE = D.pipeline || null, GHF = (D.feeds || {}).github || {};
const SVG = 'http://www.w3.org/2000/svg';
const $ = id => document.getElementById(id);
const byId = id => P.find(p => p.id === id);

// ---------- dom helpers ----------
function h(tag, attrs, ...kids){
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  add(e, kids);
  return e;
}
function s(tag, attrs, ...kids){
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null) e.setAttribute(k, v);
  add(e, kids);
  return e;
}
function add(e, kids){
  for (const k of kids.flat(9)) { if (k == null || k === false || k === '') continue; e.append(k instanceof Node ? k : document.createTextNode(String(k))); }
}

// Links from data open only when they are http or https; anything else shows as plain text.
const safe = u => typeof u === 'string' && /^https?:\/\//i.test(u.trim()) ? u.trim() : null;
function xa(url, attrs, ...kids){ return safe(url) ? h('a', Object.assign({href: safe(url), target: '_blank', rel: 'noopener'}, attrs || {}), kids) : h('span', attrs || {}, kids); }
// Text from derive.link_mentions segments; a row with no linked mention links as a whole when it has a link.
function linked(segs, text, link){
  if (segs && segs.some(x => safe(x.url))) return segs.map(x => safe(x.url) ? xa(x.url, {}, x.text) : x.text);
  return safe(link) ? xa(link, {}, text || '') : (text || '');
}
function txt(obj, f){ return linked(obj && obj[f + '_parts'], obj ? obj[f] : '', null); }
const mins = n => '~' + (n == null ? 5 : n) + ' min';
const plural = (n, w, ws) => n + ' ' + (n === 1 ? w : (ws || w + 's'));
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
function longDay(d){ if (!/^\d{4}-\d\d-\d\d/.test(d || '')) return d || ''; const t = new Date(d.slice(0, 10) + 'T12:00:00Z'); return DAYS[t.getUTCDay()] + ' ' + MON[t.getUTCMonth()] + ' ' + t.getUTCDate(); }
function md(d){ if (!/^\d{4}-\d\d-\d\d/.test(d || '')) return d || ''; return MON[+d.slice(5, 7) - 1] + ' ' + (+d.slice(8, 10)); }
function daysFrom(d){ if (!/^\d{4}-\d\d-\d\d/.test(d || '') || !D.today) return null; return Math.round((Date.parse(d.slice(0, 10)) - Date.parse(D.today)) / 864e5); }
function clock(iso){
  const t = Date.parse(iso || ''); if (isNaN(t)) return '';
  const o = {hour: '2-digit', minute: '2-digit', hour12: false};
  try { return new Intl.DateTimeFormat([], Object.assign({timeZone: D.tz}, o)).format(t); } catch (e) { return new Intl.DateTimeFormat([], o).format(t); }
}
function pct(n, d){ return d > 0 ? Math.max(0, Math.min(100, 100 * n / d)) : 0; }
function bar(p, cls){
  const v = Math.max(0, Math.min(100, Math.round(p || 0)));
  const e = h('span', {class: 'bar ' + (cls || ''), role: 'img', 'aria-label': v + ' percent'}, h('span'));
  e.firstChild.style.width = v + '%';
  return e;
}
function segs(done, total, live){
  const out = h('span', {class: 'segs', role: 'img', 'aria-label': done + ' of ' + total + ' done'});
  for (let i = 0; i < total; i++) out.append(h('span', {class: 'seg' + (i < done ? ' on' : live && i === done ? ' live' : '')}));
  return out;
}
function steps(done, total){ return total <= 30 ? segs(done, total) : bar(100 * done / total); }
function ring(p, size){
  size = size || 44; const r = (size - 6) / 2, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, p || 0));
  return s('svg', {class: 'ring', width: size, height: size, viewBox: `0 0 ${size} ${size}`, role: 'img', 'aria-label': Math.round(v) + ' percent done'},
    s('circle', {cx: size / 2, cy: size / 2, r, fill: 'none', stroke: 'var(--track-strong)', 'stroke-width': 5}),
    s('circle', {cx: size / 2, cy: size / 2, r, fill: 'none', stroke: 'var(--calm)', 'stroke-width': 5, 'stroke-dasharray': c.toFixed(1),
      'stroke-dashoffset': (c * (1 - v / 100)).toFixed(1), 'stroke-linecap': 'round', transform: `rotate(-90 ${size / 2} ${size / 2})`}),
    s('text', {x: '50%', y: '50%', dy: '.35em', 'text-anchor': 'middle', class: 'ring-t', fill: 'var(--strong)', style: size > 50 ? 'font-size:16px' : null}, String(Math.round(v))));
}
function badge(text, cls, attrs){ return h('span', Object.assign({class: 'badge ' + (cls || '')}, attrs || {}), text); }

// ---------- components ----------
// One row anatomy for every list: a mark, the text (leads with the fact that matters; long text clamps to two lines
// with the full text on hover, and wraps fully on the list pages and on phones), an optional visual under it, and
// meta on the right.
function row(o){
  return h('li', {class: 'row' + (o.cls ? ' ' + o.cls : '')},
    h('span', {class: 'mk ' + (o.mark || 'none'), 'aria-hidden': 'true'}),
    h('div', {class: 'rb'}, h('span', {class: 't', title: o.tip || null}, o.title), o.sub ? h('div', {class: 'rs'}, o.sub) : null, o.under || null),
    o.meta && o.meta.filter(Boolean).length ? h('span', {class: 'rm'}, o.meta) : null);
}
// A list that shows `cap` rows and grows in place: the same list, same rows, the button moves to the end.
function list(rows, cap){
  const ul = h('ul', {class: 'list'}, rows);
  if (cap == null || rows.length <= cap) return ul;
  rows.slice(cap).forEach(r => { r.hidden = true; });
  const more = 'Show ' + (rows.length - cap) + ' more';
  const btn = h('button', {type: 'button', class: 'more-btn', 'aria-expanded': 'false'}, more);
  btn.addEventListener('click', () => {
    const open = btn.getAttribute('aria-expanded') !== 'true';
    rows.slice(cap).forEach(r => { r.hidden = !open; });
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    btn.textContent = open ? 'Show less' : more;
    if (!open) ul.closest('section, details')?.scrollIntoView({block: 'nearest'});
  });
  return [ul, btn];
}
function section(o, ...kids){
  return h('section', {class: 'tile' + (o.cls ? ' ' + o.cls : ''), id: o.id || null, 'aria-labelledby': o.id ? o.id + '-h' : null},
    h('h3', {id: o.id ? o.id + '-h' : null}, o.href ? h('a', {href: o.href, class: 'h-link'}, o.title) : o.title,
      o.n != null ? h('span', {class: 'n'}, String(o.n)) : null, o.aside ? h('span', {class: 'aside'}, o.aside) : null),
    kids);
}
function empty(text){ return h('p', {class: 'empty'}, text); }
function fold(o, ...kids){
  if (!o.n && o.hideEmpty) return null;
  return h('details', {class: 'fold-sec', id: o.id || null}, h('summary', {}, h('b', {}, o.title), ' ', h('span', {class: 'n'}, String(o.n)), o.sub ? h('span', {class: 'fold-sub'}, ' ' + o.sub) : null),
    kids);
}
function projLink(pid){ const p = pid && byId(pid); return p ? h('a', {href: '#p-' + encodeURIComponent(p.id), class: 'pj-ref'}, p.name) : null; }

// ---------- rows ----------
function needRow(it, opts){
  opts = opts || {};
  return row({mark: it.late ? 'late' : 'dot', title: linked(it.title_parts, it.title, it.link), tip: it.title,
    under: opts.project ? projLink(it.project_id) : null,
    meta: [it.late ? badge(it.when, 'late') : it.when ? h('span', {class: 'when'}, it.when) : null,
      it.feed_old ? badge('old feed', 'soft', {title: F.feed_note ? F.feed_note.text : ''}) : null,
      h('span', {class: 'min'}, mins(it.minutes))]});
}
function runRow(r, opts){
  opts = opts || {};
  const title = r.kind === 'wait' ? [h('b', {}, r.person), ': ', linked(r.title_parts, r.title, r.link)] : linked(r.title_parts, r.title, r.link);
  const vis = r.total ? segs(r.done || 0, r.total, true) : r.pct != null ? bar(r.pct, r.late ? 'late' : r.kind === 'wait' ? 'age' : '') : null;
  return row({mark: r.late ? 'late' : 'none', cls: 'run', title, tip: (r.person ? r.person + ': ' : '') + r.title, sub: vis,
    under: opts.project ? projLink(r.project_id) : null,
    meta: [h('span', {class: 'step' + (r.late ? ' late-t' : '')}, r.step)]});
}
function winRow(w){ return row({mark: 'check', title: linked(w.title_parts, w.title, w.link), tip: w.full || w.title}); }
function lateRow(x, opts){
  opts = opts || {};
  return row({mark: 'late', title: linked(x.title_parts, x.title, x.link), tip: x.title,
    under: opts.project ? projLink(x.project_id) : null,
    meta: [badge(x.when || 'late', 'late'), x.date ? h('span', {class: 'when'}, 'due ' + md(x.date)) : null]});
}
// A shelf row: a parked item (idea, later, snoozed) or a loose end, with a quiet tag saying which.
function shelfRow(x, opts){
  opts = opts || {};
  const tag = badge(x.tag || 'later', 'tag');
  if (x.tag !== 'loose end') {
    return row({mark: 'shelf', title: linked(x.title_parts, x.title, x.link), tip: x.title, under: opts.project ? projLink(x.project_id) : null,
      meta: [tag, x.when ? h('span', {class: 'when'}, x.when) : null, h('span', {class: 'min'}, mins(x.minutes))]});
  }
  return row({mark: 'shelf', title: linked(x.title_parts, x.title, x.link), tip: x.note ? x.title + '\n' + x.note : x.title,
    under: x.note ? h('span', {class: 'sub'}, x.note) : null,
    meta: [tag, x.age != null ? h('span', {class: 'when', title: 'added ' + x.added}, x.age + 'd') : null,
      x.stale ? badge('over ' + SM.stale_days + 'd', 'soft', {title: 'Older than the ' + SM.stale_days + '-day rule'}) : null]});
}
function shelfSub(){
  const parts = [];
  if (SM.cap) parts.push(SM.loose + ' of ' + SM.cap + ' loose ends');
  if (SM.stale) parts.push(SM.stale + ' over ' + SM.stale_days + 'd');
  return SHELF.length ? 'ideas, later and loose ends' + (parts.length ? ' · ' + parts.join(' · ') : '') : 'Shelf is empty' + (SM.cap ? ' · 0 of ' + SM.cap + ' loose ends' : '');
}
function refLinks(t, max){
  const tk = t.tickets || [], sl = t.slack || [];
  const show = max ? tk.slice(0, max) : tk;
  const out = show.map(x => xa(x.url, {class: 'ref', title: x.label || x.key}, x.key));
  if (max && tk.length > max) out.push(h('a', {href: '#p-' + encodeURIComponent(t.id), class: 'ref more-ref', title: 'All tickets on the project page'}, '+' + (tk.length - max)));
  const slack = (max ? sl.filter(x => x.kind === 'channel' || !t.has_channel).slice(0, 2) : sl)
    .map(x => xa(x.url, {class: 'ref slack', title: x.label}, x.kind === 'thread' ? (max ? 'Slack thread' : x.label) : x.label));
  return [out, slack];
}

// ---------- header ----------
// The logo is only ever shown as <img src="data:...">, never inlined, so scripts inside an SVG cannot run.
const BRAND = C.brand && (C.brand.logo || C.brand.logo_dark) ? C.brand : null;
function pickLogo(){
  const img = $('logo'); if (!img || !BRAND) return;
  const dark = document.documentElement.dataset.theme === 'dark' || (document.documentElement.dataset.theme !== 'light' && matchMedia('(prefers-color-scheme: dark)').matches);
  const src = (dark ? BRAND.logo_dark : BRAND.logo) || '';
  if (src) img.setAttribute('src', src);
  img.hidden = !src;
}
function header(){
  const late = F.late || 0;
  return h('header', {},
    BRAND ? h('img', {id: 'logo', class: 'logo', alt: BRAND.name || '', hidden: true}) : null,
    h('h1', {}, h('a', {href: '#', class: 'home-link'}, C.title || 'Status')),
    h('span', {class: 'date'}, longDay(D.today) + ' · built ' + clock(D.built_at)),
    h('nav', {class: 'chips', 'aria-label': 'Counts'},
      h('a', {class: 'chip need', href: '#need', title: 'Every item that needs you'}, (F.needs || 0) + ' need you · ~' + (F.minutes || 0) + ' min'),
      late ? h('a', {class: 'chip late', href: '#late', title: 'Every late item'}, late + ' late') : null,
      h('a', {class: 'chip', href: '#running'}, RUN.length + ' running'),
      h('a', {class: 'chip', href: '#wins'}, WINS.length + ' wins today'),
      PIPE || HAS_STATS ? h('a', {class: 'chip gh', href: '#github', title: 'PR pipeline, review requests and stats'}, 'GitHub stats') : null));
}
function footer(){
  const srcBad = (D.sources || []).filter(x => x.state !== 'ok');
  const unl = D.unlinked || [];
  return h('footer', {},
    h('span', {}, 'Minutes are rough: from the data where set, otherwise a default per kind of task.'),
    srcBad.length ? h('span', {}, 'Sources: ' + srcBad.map(x => x.label + ' ' + x.state + (x.as_of ? ' (' + x.as_of + ')' : '')).join(', ') + '.') : null,
    unl.length ? h('span', {title: unl.map(u => u.text + ' at ' + u.where).join('\n')}, unl.length + ' mentions have no link.') : null,
    C.source_note ? h('span', {}, C.source_note) : null);
}
function feedNote(rows){
  return F.feed_note && rows.some(r => r.feed_old) ? h('p', {class: 'feed-note'}, 'Rows marked "old feed": ' + F.feed_note.text + '. They may be done already.') : null;
}

// ---------- home ----------
function hero(){
  const x = F.hero;
  if (!x) {
    return h('section', {class: 'hero', 'aria-labelledby': 'hero-h'}, h('div', {class: 'hero-top'}, h('span', {class: 'eyebrow'}, 'Right now')),
      h('h2', {id: 'hero-h'}, 'Nothing needs you'),
      h('p', {class: 'hero-what'}, RUN.length ? plural(RUN.length, 'thing is', 'things are') + ' running on their own. ' : 'Nothing is running either. ',
        RUN.length ? h('a', {href: '#running'}, 'See them') : null));
  }
  return h('section', {class: 'hero', 'aria-labelledby': 'hero-h'},
    h('div', {class: 'hero-top'}, h('span', {class: 'eyebrow'}, 'Do this first'),
      x.late ? badge(x.when, 'late') : x.when ? badge(x.when, 'on-hero') : null,
      badge(mins(x.minutes), 'on-hero'), x.feed_old ? badge('old feed', 'on-hero', {title: F.feed_note ? F.feed_note.text : ''}) : null),
    h('h2', {id: 'hero-h'}, x.action),
    x.detail ? h('p', {class: 'hero-what'}, linked(x.detail_parts, x.detail, null)) : null,
    h('div', {class: 'hero-foot'}, safe(x.link) ? h('a', {class: 'go', href: safe(x.link), target: '_blank', rel: 'noopener'}, x.open_label || 'Open') : null,
      x.project_id && byId(x.project_id) ? h('a', {class: 'hero-meta', href: '#p-' + encodeURIComponent(x.project_id)}, byId(x.project_id).name) : null,
      x.why ? h('span', {class: 'hero-meta'}, x.why) : null));
}
function projectCard(t){
  const p = byId(t.id) || {name: t.id};
  return h('li', {class: 'pcard'},
    ring(t.pct, 46),
    h('div', {class: 'pc-body'},
      h('a', {class: 'pc-name', href: '#p-' + encodeURIComponent(t.id), title: p.name}, p.name),
      h('div', {class: 'pc-meta'}, p.priority ? h('b', {class: 'prio'}, p.priority) : null, p.status ? h('span', {}, p.status) : null,
        t.steps_total ? h('span', {class: 'pc-steps'}, steps(t.steps_done, t.steps_total), h('span', {class: 'step'}, t.steps_done + ' of ' + t.steps_total + ' steps')) : null),
      t.next ? h('p', {class: 'pc-next', title: t.next}, h('span', {class: 'lbl'}, 'Next '), linked(t.next_parts, t.next, null)) : null,
      h('div', {class: 'pc-refs'}, refLinks(t, 2), !(t.tickets || []).length && !(t.slack || []).length ? h('span', {class: 'muted'}, 'No ticket or channel in the data') : null)),
    h('div', {class: 'pc-badges'}, t.late ? badge(t.late + ' late', 'late') : null, t.needs ? badge(t.needs + ' for you', 'need') : null));
}
function homePage(){
  const up = F.up_next || [];
  const upTile = section({id: 'up', title: 'Up next', n: up.length, href: '#need', aside: up.length ? h('a', {href: '#need'}, 'All ' + NEEDS.length) : null},
    up.length ? list(up.map(i => needRow(i)), UP_N) : empty('Nothing else needs you.'), feedNote(NEEDS));
  const shelf = fold({id: 'shelf', title: 'Shelf', n: SHELF.length, sub: shelfSub()},
    SHELF.length ? [list(SHELF.map(x => shelfRow(x)), CAP), h('a', {href: '#shelf', class: 'fold-all'}, 'Open the shelf page')] : empty('Shelf is empty.'));
  const pj = section({id: 'pj', title: 'Projects in progress', n: TILES.length, cls: 'projects', aside: 'by priority'},
    TILES.length ? list(TILES.map(projectCard), CAP) : empty('No projects yet.'));
  const runTile = section({id: 'run', title: 'Running without you', n: RUN.length, href: '#running'}, RUN.length ? list(RUN.map(r => runRow(r)), CAP) : empty('Nothing is running.'));
  const merged = F.merged_this_week ? h('a', {href: '#github'}, F.merged_this_week + ' PRs merged this week') : null;
  const winTile = section({id: 'win', title: 'Wins today', n: WINS.length, href: '#wins', aside: merged}, WINS.length ? list(WINS.map(winRow), CAP) : empty('Nothing done yet today.'));
  return [h('div', {class: 'grid'}, h('div', {class: 'col'}, hero(), upTile, shelf), h('div', {class: 'col'}, pj), h('div', {class: 'col'}, runTile, winTile))];
}

// ---------- list pages (every header count opens one) ----------
function subpage(title, sub, ...kids){
  return [h('div', {class: 'sub-head'}, h('a', {href: '#', class: 'back'}, '← Today'), h('h2', {}, title), sub ? h('span', {class: 'muted'}, sub) : null), kids];
}
function needPage(){
  return subpage('Needs you', plural(NEEDS.length, 'item') + ', about ' + (F.minutes || 0) + ' min',
    section({title: 'In order: do the top one first', n: NEEDS.length}, NEEDS.length ? list(NEEDS.map(i => needRow(i, {project: true}))) : empty('Nothing needs you right now.'), feedNote(NEEDS)),
    SHELF.length ? h('p', {class: 'muted'}, 'Not counted here: ', h('a', {href: '#shelf'}, plural(SHELF.length, 'item') + ' on the shelf'), '.') : null);
}
function latePage(){
  return subpage('Late', plural(LATE.length, 'item') + ' past their date',
    section({title: 'Late items', n: LATE.length}, LATE.length ? list(LATE.map(x => lateRow(x, {project: true}))) : empty('Nothing is late.')));
}
function runningPage(){
  const groups = [['today', 'Today\'s milestones'], ['job', 'Long jobs'], ['delivered', 'Delivered, waiting for a confirm'], ['confirm', 'To confirm'], ['oneoff', 'Other items'], ['wait', 'Waiting on people']];
  return subpage('Running without you', plural(RUN.length, 'item'), groups.map(([k, label]) => {
    const rs = RUN.filter(r => r.kind === k);
    return rs.length ? section({title: label, n: rs.length}, list(rs.map(r => runRow(r, {project: true})))) : null;
  }), RUN.length ? null : empty('Nothing is running.'));
}
function winsPage(){
  return subpage('Wins today', plural(WINS.length, 'win'),
    section({title: 'Done today', n: WINS.length, aside: F.merged_this_week ? h('a', {href: '#github'}, F.merged_this_week + ' PRs merged this week') : null},
      WINS.length ? list(WINS.map(winRow)) : empty('Nothing done yet today.')));
}
function shelfPage(){
  return subpage('Shelf', shelfSub(), section({title: 'Ideas, later, snoozed and loose ends', n: SHELF.length},
    SHELF.length ? list(SHELF.map(x => shelfRow(x, {project: true}))) : empty('Shelf is empty.')));
}

// ---------- project page ----------
const STATE_CLASS = st => 's-' + String(st || 'not started').toLowerCase().replace(/\s+/g, '-');
function projectPage(id){
  const p = byId(id);
  if (!p) return subpage('Project not found', 'No project with id ' + id);
  const t = TILES.find(x => x.id === id) || {tickets: [], slack: [], steps_done: 0, steps_total: 0};
  const late = LATE.filter(x => x.project_id === id);
  const needs = NEEDS.filter(x => x.project_id === id);
  const parked = SHELF.filter(x => x.project_id === id);
  const run = RUN.filter(x => x.project_id === id);
  const head = h('section', {class: 'tile pj-head'}, ring(p.progress_pct, 76),
    h('div', {class: 'pj-hb'},
      h('div', {class: 'pc-meta'}, p.priority ? h('b', {class: 'prio'}, p.priority) : null, p.status ? h('span', {}, p.status) : null,
        p.epic ? h('span', {}, 'epic ', txt(p, 'epic')) : null,
        p.deadline ? h('span', {class: daysFrom(p.deadline) < 0 && (p.progress_pct || 0) < 100 ? 'late-t' : ''}, 'deadline ' + longDay(p.deadline)) : null),
      t.steps_total ? h('div', {class: 'pc-steps wide'}, steps(t.steps_done, t.steps_total), h('span', {class: 'step'}, t.steps_done + ' of ' + t.steps_total + ' steps done')) : null,
      h('div', {class: 'pc-refs'}, h('span', {class: 'lbl'}, 'Tickets'), (t.tickets || []).length ? refLinks({tickets: t.tickets, slack: []}) : h('span', {class: 'muted'}, 'none in the data')),
      h('div', {class: 'pc-refs'}, h('span', {class: 'lbl'}, 'Slack'), (t.slack || []).length ? refLinks({tickets: [], slack: t.slack}) : h('span', {class: 'muted'}, 'none in the data')),
      p.summary ? h('p', {class: 'pj-sum'}, txt(p, 'summary')) : null));
  const left = [
    late.length ? section({title: 'Late', n: late.length, cls: 'is-late'}, list(late.map(x => lateRow(x)))) : null,
    section({title: 'Needs you', n: needs.length}, needs.length ? list(needs.map(i => needRow(i))) : empty('Nothing. This one moves without you.'),
      parked.length ? h('p', {class: 'muted small'}, 'Also on the shelf: ') : null, parked.length ? list(parked.map(i => shelfRow(i))) : null),
    p.next_milestone || p.progress_basis ? section({title: 'Next'}, p.next_milestone ? h('p', {class: 'pj-line'}, txt(p, 'next_milestone'), p.next_milestone_date ? h('span', {class: 'when'}, ' (' + md(p.next_milestone_date) + ')') : null) : null,
      p.progress_basis ? h('p', {class: 'pj-line muted'}, 'How the ' + (p.progress_pct || 0) + '% was worked out: ' + p.progress_basis) : null) : null,
    run.length ? section({title: 'Running without you', n: run.length}, list(run.map(r => runRow(r)), CAP)) : null];
  const groups = (p.breakdown || []).map(g => {
    const gi = g.items || [], gd = gi.filter(i => i.state === 'done').length;
    return h('div', {class: 'bd-g'}, h('div', {class: 'bd-h'}, h('b', {}, g.group || ''), h('span', {class: 'step'}, gd + ' of ' + gi.length)),
      gi.length ? segs(gd, gi.length) : null,
      h('ul', {}, gi.map(i => h('li', {class: 'bd-i ' + STATE_CLASS(i.state)}, h('span', {class: 'st'}, i.state || ''),
        h('span', {}, txt(i, 'text'), i.ref && String(i.text || '').indexOf(i.ref) < 0 ? [' ', h('span', {class: 'muted'}, linked(i.ref_parts, i.ref, safe(i.ref) ? i.ref : null))] : null,
          (i.links || []).filter(l => safe(l.url)).map(l => [' ', xa(l.url, {}, l.label || 'link')]))))));
  });
  const prog = (p.recent_progress || []).map(r => row({mark: 'none', title: txt(r, 'text'), tip: r.text, meta: [h('span', {class: 'when'}, md(r.date))]}));
  const dec = (p.decisions || []).map(d => row({mark: 'none', title: txt(d, 'decision'), tip: d.decision, meta: [h('span', {class: 'when'}, md(d.date))]}));
  const links = (p.links || []).filter(l => safe(l.url));
  const right = [
    groups.length ? section({title: 'Breakdown', n: t.steps_done + ' of ' + t.steps_total}, h('div', {class: 'bd'}, groups)) : null,
    prog.length ? section({title: 'Recent progress', n: prog.length}, list(prog, CAP)) : null,
    dec.length ? section({title: 'Decisions', n: dec.length}, list(dec, CAP)) : null,
    links.length ? section({title: 'Links', n: links.length}, h('div', {class: 'pj-links'}, links.map(l => xa(l.url, {}, l.label || l.url)))) : null];
  return subpage(p.name, null, head, h('div', {class: 'two'}, h('div', {class: 'col'}, left), h('div', {class: 'col'}, right)));
}

// ---------- GitHub stats page ----------
let CHARTS = [];
function chart(name, draw, data){ const el = h('div', {class: 'chart', 'data-chart': name}); CHARTS.push({el, draw, data, w: 0}); return el; }
function drawCharts(force){
  CHARTS = CHARTS.filter(c => c.el.isConnected);
  CHARTS.forEach(c => { const w = Math.max(240, Math.floor(c.el.getBoundingClientRect().width || 0)); if (force || Math.abs(w - c.w) > 40) { c.w = w; c.el.replaceChildren(c.draw(c.data, w)); } });
}
function niceMax(m){ for (const v of [4, 6, 8, 10, 12, 16, 20, 24, 30, 40, 60, 80, 100, 120, 160, 200]) if (v >= m) return v; return Math.ceil(m / 100) * 100; }
function spark(values){
  const pts0 = (values || []).map((v, i) => [i, v]).filter(q => q[1] != null);
  const w = 110, hgt = 38, pad = 4;
  const svg = s('svg', {class: 'sp-svg', viewBox: `0 0 ${w} ${hgt}`, preserveAspectRatio: 'none', 'aria-hidden': 'true'});
  if (pts0.length < 2) return svg;
  const vs = pts0.map(q => q[1]), mx = Math.max(...vs), mn = Math.min(...vs), n = (values.length - 1) || 1;
  const pts = pts0.map(q => [pad + q[0] * (w - 2 * pad) / n, pad + (hgt - 2 * pad) * (1 - (q[1] - mn) / ((mx - mn) || 1))]);
  const d = pts.map((q, i) => (i ? 'L' : 'M') + q[0].toFixed(1) + ',' + q[1].toFixed(1)).join('');
  const L = pts[pts.length - 1];
  svg.append(s('path', {class: 'sp-a', d: `${d}L${L[0].toFixed(1)},${hgt}L${pts[0][0].toFixed(1)},${hgt}Z`}), s('path', {class: 'sp-l', d}),
    s('circle', {class: 'sp-d', cx: L[0].toFixed(1), cy: L[1].toFixed(1), r: 3.5}));
  return svg;
}
// Merged per week: gridlines at 0, half and max, every third week labeled, the current week highlighted.
function colBars(data, Wd){
  const v = data.values, labels = data.labels, H = 190, pl = 28, pr = 6, pt = 18, pb = 22, iw = Wd - pl - pr, ih = H - pt - pb;
  const mx = niceMax(Math.max(1, ...v)), n = v.length || 1, slot = iw / n, bw = Math.max(6, Math.min(40, slot - 8));
  const svg = s('svg', {class: 'th-svg', viewBox: `0 0 ${Wd} ${H}`, width: Wd, height: H, role: 'img', 'aria-label': data.aria});
  for (const t of [0, mx / 2, mx]) {
    const y = pt + ih - ih * t / mx;
    svg.append(s('line', {class: 'th-grid', x1: pl, x2: Wd - pr, y1: y, y2: y}), s('text', {class: 'th-axis', x: pl - 6, y: y + 4, 'text-anchor': 'end'}, String(t)));
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
function fill(cls, width){ const e = h('div', {class: cls}); e.style.width = width + '%'; return e; }
function rowBars(rows){
  const mx = Math.max(1, ...rows.map(r => r.n || 0));
  return h('div', {class: 'th-load'}, rows.map(r => h('div', {class: 'th-row'}, h('span', {}, r.label),
    h('div', {class: 'trk'}, fill('fill ' + r.cls, pct(r.n || 0, mx))), h('span', {class: 'th-n num'}, r.n == null ? 'n/a' : r.n))));
}
// Hours: under 1h in minutes, under 10h one decimal, under 48h whole hours, else days with one decimal.
function fmtH(hrs){
  if (hrs == null) return ['n/a', ''];
  if (hrs < 1) return [String(Math.round(hrs * 60)), 'm median'];
  if (hrs < 10) return [hrs.toFixed(1), 'h median'];
  if (hrs < 48) return [String(Math.round(hrs)), 'h median'];
  return [(hrs / 24).toFixed(1), 'd median'];
}
function tickBar(label, st, max){
  if (!st || st.median == null) return h('div', {class: 'tk-row'}, h('span', {}, label), h('span', {class: 'muted'}, 'n/a'));
  const m = fmtH(st.median), q = fmtH(st.p90);
  const tick = h('span', {class: 'tk-tick'}); tick.style.left = pct(st.p90, max) + '%';
  return h('div', {class: 'tk-row'}, h('span', {}, label),
    h('div', {class: 'trk', role: 'img', 'aria-label': label + ': median ' + m.join('') + ', p90 ' + q.join('')}, fill('fill', pct(st.median, max)), tick),
    h('span', {class: 'tk-n num'}, h('b', {}, m[0] + m[1].split(' ')[0]), ' p90 ' + q[0] + q[1].split(' ')[0]));
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
function pill(p, stageKey){
  const cls = {draft: 'draft', review: 'rev', approved: 'ok', merged: 'done'}[stageKey];
  const flags = [p.ci_failed ? 'CI failed' : null, p.conflict ? 'conflict' : null].filter(Boolean);
  const title = p.title + (flags.length ? ' (' + flags.join(', ') + ')' : '');
  return xa(p.url, {class: 'pl-pill ' + cls, title, 'aria-label': p.label + ': ' + title}, p.label, flags.length ? ' ' + flags.join(', ') : null);
}
function segmented(label, items){
  return h('div', {class: 'segd', role: 'group', 'aria-label': label}, items.map(it =>
    h('a', {href: it.disabled ? null : it.href, 'aria-current': it.on ? 'true' : null, 'aria-disabled': it.disabled ? 'true' : null, title: it.title || null}, it.label)));
}
function ghChoice(arg){
  const m = /^(me|team)-(30|90)$/.exec(arg || '');
  const c = m ? {group: m[1], win: m[2]} : {group: 'me', win: '30'};
  if (!GROUPS[c.group]) c.group = GROUPS.me || !GROUPS.team ? 'me' : 'team';
  return c;
}
function githubPage(arg){
  CHARTS = [];
  const c = ghChoice(arg);
  const ghOld = F.feed_note && (F.feed_note.sources || []).indexOf('github') >= 0;
  const owed = (GHF.review_requests || []);
  const pipeline = PIPE ? section({title: 'PR pipeline', aside: PIPE.stale ? badge('stale', 'soft', {title: 'The GitHub feed is failing; these stages may be out of date'}) : null},
    PIPE.stages.some(x => x.n) ? [flowBar(PIPE.stages), PIPE.stages.map(st => h('div', {class: 'pl-stage'}, h('span', {class: 'pl-sn'}, st.label), h('span', {class: 'pl-sc num'}, st.n),
      h('span', {class: 'pl-pills'}, st.pills.map(q => pill(q, st.key)))))] : empty('No open PRs.')) : section({title: 'PR pipeline'}, empty('No GitHub feed on this machine.'));
  const reviews = section({title: 'Reviews asked of you', n: owed.length}, owed.length ? list(owed.map(r => {
    const ago = r.requested_at ? -daysFrom(r.requested_at.slice(0, 10)) : null;
    return row({mark: 'dot', title: xa(r.url, {}, r.title || r.url), tip: r.title,
      meta: [h('span', {class: 'when'}, [r.author, ((r.additions || 0) + (r.deletions || 0)) + ' lines', ago != null ? (ago > 0 ? 'asked ' + ago + 'd ago' : 'asked today') : null].filter(Boolean).join(' · '))]});
  })) : empty('No reviews waiting on you.'));
  const top = [ghOld ? h('p', {class: 'feed-note'}, F.feed_note.text + '. The pipeline and reviews may be behind.') : null, h('div', {class: 'two'}, pipeline, reviews)];
  if (!HAS_STATS) return subpage('GitHub stats', null, top, section({title: 'Stats'}, empty('Stats are not ready: ' + ((ST && ST.error) || 'no data') + '. Run eng-stats doctor.')));
  const g = GROUPS[c.group] || {}, wk = g.weekly || {}, w = (g.windows || {})[c.win] || {};
  const noTeam = !GROUPS.team;
  const toggles = h('div', {class: 'gh-tg'},
    segmented('Whose numbers', [{label: 'Me', on: c.group === 'me', href: '#github-me-' + c.win}, {label: 'Team', on: c.group === 'team', disabled: noTeam, title: noTeam ? 'Set stats.team_slug or stats.team_members' : null, href: '#github-team-' + c.win}]),
    segmented('Time range', [{label: '30d', on: c.win === '30', href: '#github-' + c.group + '-30'}, {label: '90d', on: c.win === '90', href: '#github-' + c.group + '-90'}]));
  const k = (label, val, unit, series) => h('div', {class: 'kp'}, h('span', {class: 'kp-l'}, label),
    h('span', {class: 'kp-v num' + (val === 'n/a' ? ' muted' : '')}, val, unit ? h('em', {}, unit) : null), spark(series));
  const f = fmtH((w.ttfr_h || {}).median), m = fmtH((w.ttm_h || {}).median);
  const kpis = h('div', {class: 'kp-row'}, k('PRs merged', w.merged == null ? 'n/a' : w.merged, '', wk.merged), k('Reviews given', w.reviews_given == null ? 'n/a' : w.reviews_given, '', wk.given),
    k('Time to first review', f[0], f[1], wk.ttfr_h), k('Time to merge', m[0], m[1], wk.ttm_h));
  const vals = wk.merged || [], labels = wk.weeks || [], given = w.reviews_given || 0, recv = w.reviews_received || 0;
  const who = c.group === 'team' ? 'Team' : 'Me';
  const thru = section({title: 'Throughput', aside: who + ', last ' + c.win + ' days'}, h('div', {class: 'th-grid2'},
    h('div', {}, h('p', {class: 'th-sub'}, 'PRs merged per week, last ' + vals.length + ' weeks'),
      chart('weekly', colBars, {values: vals, labels, aria: 'PRs merged per week: ' + vals.join(', ')}),
      h('details', {class: 'th-tbl'}, h('summary', {}, 'Show as table'), h('div', {class: 'th-x'}, h('table', {},
        h('tr', {}, h('th', {}, 'Week of'), labels.map(l => h('th', {}, md(l)))), h('tr', {}, h('td', {}, 'Merged'), vals.map(v => h('td', {}, v))))))),
    h('div', {}, h('p', {class: 'th-sub'}, 'Review load'),
      rowBars([{label: 'Given', n: given, cls: 'is-c1'}, {label: 'Received', n: recv, cls: 'is-c2'}]),
      recv > 0 ? h('div', {class: 'th-ratio'}, h('b', {class: 'num'}, (given / recv).toFixed(1) + 'x'), ' given for each received') : null)));
  const fr = w.ttfr_h || {}, mg = w.ttm_h || {}, max = Math.max(fr.p90 || 0, mg.p90 || 0) * 1.1 || 1;
  const turn = (w.merged || 0) < 5 ? empty('Too few merged PRs in this window to show turnaround.')
    : [tickBar('First review', fr, max), tickBar('Merge', mg, max), h('p', {class: 'muted small'}, plural(w.merged_no_review || 0, 'PR') + ' merged with no review, ' + plural(w.re_reviews || 0, 're-review'))];
  const groups = w.by_repo_group || {}, onlyOther = Object.keys(groups).filter(x => groups[x] > 0).every(x => x === 'other');
  const cov = ST.coverage || {}, org = ST.org || C.github_org;
  const q = org && cov.from && cov.to ? 'https://github.com/search?type=pullrequests&q=' + encodeURIComponent('org:' + org + ' is:pr updated:' + cov.from + '..' + cov.to) : null;
  const note = ST.ok === false ? h('p', {class: 'feed-note'}, 'Stats did not refresh: ' + (ST.error || 'unknown error') + ' (data to ' + (cov.to || '?') + ')') : null;
  return subpage('GitHub stats', null, top, h('div', {class: 'gh-bar'}, toggles), note, kpis, thru,
    h('div', {class: 'two'}, section({title: 'Turnaround', aside: who + ', last ' + c.win + ' days'}, turn),
      onlyOther ? null : section({title: 'By repo group', aside: plural(w.merged || 0, 'PR') + ' merged'}, stackBar(groups))),
    h('p', {class: 'muted small'}, 'Excluded: ' + plural((ST.excluded || {}).bot_prs || 0, 'bot PR') + '. Lines of code: off. ',
      q ? xa(q, {}, 'Data from ' + cov.from + ' to ' + cov.to) : 'Data from ' + (cov.from || '?') + ' to ' + (cov.to || '?'), '.',
      cov.truncated_windows > 0 ? " Some busy hours hit GitHub's search cap; counts may be a little low." : null));
}

// ---------- router ----------
const ROUTES = {need: needPage, late: latePage, running: runningPage, wins: winsPage, shelf: shelfPage, github: githubPage};
const OLD = {parked: 'shelf', inbox: 'need', stats: 'github', prs: 'github', waiting: 'running', people: 'running', delivered: 'running', home: '', overview: ''};
function route(){
  let hash = '';
  try { hash = decodeURIComponent((location.hash || '').slice(1)); } catch (e) { hash = ''; }  // a malformed hash opens home
  const base = hash.split(/[/-]/)[0];
  if (OLD[base] != null) hash = OLD[base] + (base === 'stats' && hash.length > 6 ? '-' + hash.slice(6).replace('/', '-') : '');
  let body, name = 'home';
  const pm = /^p-(.+)$/.exec(hash);
  if (pm) { body = projectPage(pm[1]); name = 'project'; }
  else if (hash.startsWith('github')) { body = githubPage(hash.slice(7)); name = 'github'; }
  else if (ROUTES[hash]) { body = ROUTES[hash](); name = hash; }
  else body = homePage();
  $('page').replaceChildren(header(), h('main', {class: 'body', 'data-page': name}, body), footer());
  document.body.dataset.page = name;
  document.title = C.title || document.title;
  pickLogo();
  drawCharts(true);
  if (name !== 'home') scrollTo(0, 0);
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

route();
tooltip();
addEventListener('hashchange', route);
addEventListener('resize', () => drawCharts(false));
addEventListener('keydown', e => { if (e.key === 'Escape' && location.hash && location.hash !== '#') location.hash = ''; });
try { matchMedia('(prefers-color-scheme: dark)').addEventListener('change', pickLogo); } catch (e) { /* older browsers */ }
new MutationObserver(pickLogo).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
