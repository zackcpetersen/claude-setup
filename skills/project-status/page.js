// Status page script. build.py inlines this file, page.css and the data into template.html.
// One screen: the "Do this first" hero, Up next, Running without you, Wins today, Parked, and a strip of
// project rings that open for detail. #p-<id> opens that project. Older hashes (#inbox, #stats...) show the same page.
// Every number, label and grouping is worked out in derive.py (focus_view); this file only lays the data out.
const D = JSON.parse(document.getElementById('data').textContent);
const C = D.config || {};
const P = D.projects || [], W = D.waiting_on || [];
const F = D.focus || {hero: null, up_next: [], running: [], wins: [], parked: [], tiles: [], cap: 5, up_next_shown: 3};
const CAP = F.cap || 5, UP_N = F.up_next_shown || 3;
const SVG = 'http://www.w3.org/2000/svg';
const $ = id => document.getElementById(id);

function h(tag, attrs, ...kids){
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else e.setAttribute(k, v === true ? '' : v);
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
const mins = n => '~' + (n || 5) + ' min';
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
function longDay(d){ if (!/^\d{4}-\d\d-\d\d/.test(d || '')) return d || ''; const t = new Date(d.slice(0, 10) + 'T12:00:00Z'); return DAYS[t.getUTCDay()] + ' ' + MON[t.getUTCMonth()] + ' ' + t.getUTCDate(); }
function clock(iso){
  const t = Date.parse(iso || ''); if (isNaN(t)) return '';
  const o = {hour: '2-digit', minute: '2-digit', hour12: false};
  try { return new Intl.DateTimeFormat([], Object.assign({timeZone: D.tz}, o)).format(t); } catch (e) { return new Intl.DateTimeFormat([], o).format(t); }
}
function bar(pct, cls){
  const v = Math.max(0, Math.min(100, Math.round(pct || 0)));
  const e = h('span', {class: 'bar ' + (cls || ''), role: 'img', 'aria-label': v + ' percent'}, h('span'));
  e.firstChild.style.width = v + '%';
  return e;
}
function segs(done, total, live){
  const out = h('span', {class: 'segs', role: 'img', 'aria-label': done + ' of ' + total + ' done'});
  for (let i = 0; i < total; i++) out.append(h('span', {class: 'seg' + (i < done ? ' on' : live && i === done ? ' live' : '')}));
  return out;
}
function ring(pct, size){
  size = size || 44; const r = (size - 6) / 2, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, pct || 0));
  return s('svg', {class: 'ring', width: size, height: size, viewBox: `0 0 ${size} ${size}`, 'aria-hidden': 'true'},
    s('circle', {cx: size / 2, cy: size / 2, r, fill: 'none', stroke: 'var(--track-strong)', 'stroke-width': 5}),
    s('circle', {cx: size / 2, cy: size / 2, r, fill: 'none', stroke: 'var(--calm)', 'stroke-width': 5, 'stroke-dasharray': c.toFixed(1),
      'stroke-dashoffset': (c * (1 - v / 100)).toFixed(1), 'stroke-linecap': 'round', transform: `rotate(-90 ${size / 2} ${size / 2})`}),
    s('text', {x: '50%', y: '50%', dy: '.35em', 'text-anchor': 'middle', class: 'ring-t', fill: 'var(--strong)'}, String(Math.round(v))));
}
// A list: the first `shown` rows, the rest folded behind "Show N more". Nothing is dropped.
function folded(rows, shown){
  const frag = [h('ul', {class: 'list'}, rows.slice(0, shown))];
  if (rows.length > shown) frag.push(h('details', {class: 'more'}, h('summary', {}, 'Show ' + (rows.length - shown) + ' more'), h('ul', {class: 'list more-body'}, rows.slice(shown))));
  return frag;
}
function feedNote(rows){
  return F.feed_note && rows.some(r => r.feed_old) ? h('p', {class: 'feed-note'}, F.feed_note.text + '. These rows may be behind.') : null;
}

// ---------- pieces ----------
function needRow(it){
  return h('li', {class: 'row need'}, h('span', {class: 'dot', 'aria-hidden': 'true'}),
    h('span', {class: 't', title: it.title}, linked(it.title_parts, it.title, it.link)),
    it.late ? h('span', {class: 'badge late'}, it.when) : it.when ? h('span', {class: 'when'}, it.when) : null,
    it.feed_old ? h('span', {class: 'badge soft', title: F.feed_note ? F.feed_note.text : ''}, 'old feed') : null,
    h('span', {class: 'min'}, mins(it.minutes)));
}
function runRow(r){
  const title = r.kind === 'wait' ? [h('b', {}, r.person), ': ', linked(r.title_parts, r.title, r.link)] : linked(r.title_parts, r.title, r.link);
  const vis = r.total ? segs(r.done || 0, r.total, true) : r.pct != null ? bar(r.pct, r.late ? 'late' : r.kind === 'wait' ? 'age' : '') : null;
  return h('li', {class: 'row run'}, h('div', {class: 'rt'}, h('span', {class: 't', title: (r.person ? r.person + ': ' : '') + r.title}, title),
    h('span', {class: 'step' + (r.late ? ' late-t' : '')}, r.step)), vis);
}
function winRow(w){
  return h('li', {class: 'row win'}, h('span', {class: 'check', 'aria-hidden': 'true'}), h('span', {class: 't', title: w.full || w.title}, linked(w.title_parts, w.title, w.link)));
}

function hero(){
  const x = F.hero;
  if (!x) {
    return h('section', {class: 'hero', 'aria-labelledby': 'hero-h'}, h('div', {class: 'hero-top'}, h('span', {class: 'eyebrow'}, 'Right now')),
      h('h2', {id: 'hero-h'}, 'Nothing needs you'),
      h('p', {class: 'hero-what'}, F.running.length ? F.running.length + ' things are running on their own. See "Running without you".' : 'Nothing is running either.'));
  }
  const meta = [x.project, x.why].filter(Boolean).join(' - ');
  return h('section', {class: 'hero', 'aria-labelledby': 'hero-h'},
    h('div', {class: 'hero-top'}, h('span', {class: 'eyebrow'}, 'Do this first'),
      x.late ? h('span', {class: 'badge late'}, x.when) : x.when ? h('span', {class: 'badge on-hero'}, x.when) : null,
      h('span', {class: 'badge on-hero'}, mins(x.minutes))),
    h('h2', {id: 'hero-h'}, x.action),
    x.detail_parts && x.detail_parts.length ? h('p', {class: 'hero-what'}, linked(x.detail_parts, '', null)) : null,
    x.feed_old && F.feed_note ? h('p', {class: 'hero-what small'}, F.feed_note.text + '. This may be done already.') : null,
    h('div', {class: 'hero-foot'}, safe(x.link) ? h('a', {class: 'go', href: safe(x.link), target: '_blank', rel: 'noopener'}, x.open_label || 'Open') : null,
      meta ? h('span', {class: 'hero-meta'}, meta) : null));
}

function projectTile(p, t){
  const items = [];
  (p.breakdown || []).forEach(g => (g.items || []).forEach(i => items.push(i)));
  const nm = p.next_milestone ? h('p', {class: 'pj-line'}, h('b', {}, 'Next: '), txt(p, 'next_milestone')) : null;
  const asks = (p.needs_me || []).map(n => h('li', {}, linked(n.ask_parts, n.ask, n.link), n.due ? h('span', {class: 'when'}, ' due ' + n.due.slice(5)) : null));
  const waits = W.filter(w => w.project_id === p.id).map(w => h('li', {}, h('b', {}, w.person || 'someone'), ': ', linked(w.what_parts, w.what, w.link)));
  const groups = (p.breakdown || []).map(g => {
    const gi = g.items || [], gd = gi.filter(i => i.state === 'done').length;
    return h('div', {class: 'bd-g'}, h('div', {class: 'bd-h'}, h('b', {}, g.group || ''), h('span', {class: 'step'}, gd + ' of ' + gi.length)),
      h('ul', {}, gi.map(i => h('li', {class: 'bd-i s-' + String(i.state || '').replace(/\s+/g, '-')}, h('span', {class: 'st'}, i.state || ''),
        h('span', {}, txt(i, 'text'), i.ref ? [' ', linked(i.ref_parts, '', safe(i.ref) ? i.ref : null)] : null)))));
  });
  const prog = (p.recent_progress || []).slice(0, 5).map(r => h('li', {}, h('span', {class: 'when'}, (r.date || '').slice(5) + ' '), txt(r, 'text')));
  const links = (p.links || []).filter(l => safe(l.url)).map(l => xa(l.url, {}, l.label || l.url));
  const small = items.length <= 30;
  return h('details', {class: 'proj', id: 'p-' + p.id},
    h('summary', {}, ring(p.progress_pct),
      h('span', {class: 'pj-body'}, h('span', {class: 'pj-name', title: p.name}, p.name),
        h('span', {class: 'pj-meta'}, [p.priority, p.status].filter(Boolean).join(' · '),
          t.needs ? h('span', {class: 'badge need'}, t.needs + ' for you') : null, t.late ? h('span', {class: 'badge late'}, t.late + ' late') : null),
        items.length ? h('span', {class: 'pj-steps'}, small ? segs(t.steps_done, t.steps_total) : bar(100 * t.steps_done / t.steps_total), h('span', {class: 'step'}, t.steps_done + ' of ' + t.steps_total + ' steps')) : null)),
    h('div', {class: 'pj-detail'},
      h('p', {class: 'pj-line'}, h('b', {}, txt(p, 'name')), p.epic ? [' (', txt(p, 'epic'), ')'] : null, p.deadline ? h('span', {class: 'when'}, ' - deadline ' + p.deadline) : null),
      nm,
      p.progress_basis ? h('p', {class: 'pj-line muted'}, p.progress_basis) : null,
      asks.length ? h('div', {}, h('b', {}, 'Needs you'), h('ul', {class: 'plain'}, asks)) : null,
      waits.length ? h('div', {}, h('b', {}, 'Waiting on'), h('ul', {class: 'plain'}, waits)) : null,
      groups.length ? h('div', {class: 'bd'}, groups) : null,
      prog.length ? h('div', {}, h('b', {}, 'Recent progress'), h('ul', {class: 'plain'}, prog)) : null,
      links.length ? h('div', {class: 'pj-links'}, links) : null));
}

// The logo is only ever shown as <img src="data:...">, never inlined, so scripts inside an SVG cannot run.
const BRAND = C.brand && (C.brand.logo || C.brand.logo_dark) ? C.brand : null;
function pickLogo(){
  const img = $('logo'); if (!img || !BRAND) return;
  const dark = document.documentElement.dataset.theme === 'dark' || (document.documentElement.dataset.theme !== 'light' && matchMedia('(prefers-color-scheme: dark)').matches);
  const src = (dark ? BRAND.logo_dark : BRAND.logo) || '';
  if (src) img.setAttribute('src', src);
  img.hidden = !src;
}

function render(){
  const page = $('page');
  const up = F.up_next || [], run = F.running || [], wins = F.wins || [], parked = F.parked || [];
  const late = F.late || 0;
  const header = h('header', {},
    BRAND ? h('img', {id: 'logo', class: 'logo', alt: BRAND.name || '', hidden: true}) : null,
    h('h1', {}, C.title || 'Status'),
    h('span', {class: 'date'}, longDay(D.today) + ' · built ' + clock(D.built_at)),
    h('div', {class: 'chips'},
      h('span', {class: 'chip need'}, (F.needs || 0) + ' need you · ~' + (F.minutes || 0) + ' min'),
      late ? h('span', {class: 'chip late'}, late + ' late') : null,
      h('span', {class: 'chip'}, run.length + ' running'),
      h('span', {class: 'chip'}, wins.length + ' wins today')));

  const upTile = h('section', {class: 'tile', 'aria-labelledby': 'up-h'}, h('h3', {id: 'up-h'}, 'Up next ', h('span', {class: 'n'}, String(up.length))),
    feedNote(up), up.length ? folded(up.map(needRow), UP_N) : h('p', {class: 'empty'}, 'Nothing else needs you.'));
  const park = h('details', {class: 'park'}, h('summary', {}, h('b', {}, 'Parked'), ' · ' + parked.length + ' ideas and later items'),
    parked.length ? folded(parked.map(needRow), CAP) : h('p', {class: 'empty'}, 'Nothing parked.'));
  const runTile = h('section', {class: 'tile', 'aria-labelledby': 'run-h'}, h('h3', {id: 'run-h'}, 'Running without you ', h('span', {class: 'n'}, String(run.length))),
    run.length ? folded(run.map(runRow), CAP) : h('p', {class: 'empty'}, 'Nothing is running.'));
  const merged = F.merged_this_week ? h('span', {class: 'aside'}, xa('https://github.com/pulls?q=is%3Apr+author%3A%40me+is%3Amerged', {}, F.merged_this_week + ' PRs merged this week')) : null;
  const winTile = h('section', {class: 'tile', 'aria-labelledby': 'win-h'}, h('h3', {id: 'win-h'}, 'Wins today ', h('span', {class: 'n'}, String(wins.length)), merged),
    F.feed_note && F.feed_note.sources.indexOf('github') >= 0 && merged ? h('p', {class: 'feed-note'}, F.feed_note.text + '.') : null,
    wins.length ? folded(wins.map(winRow), CAP) : h('p', {class: 'empty'}, 'Nothing done yet today.'));

  const tiles = new Map((F.tiles || []).map(t => [t.id, t]));
  const projs = h('section', {'aria-labelledby': 'pj-h'}, h('h3', {id: 'pj-h', class: 'sr'}, 'Projects'),
    h('div', {class: 'projs'}, P.map(p => projectTile(p, tiles.get(p.id) || {needs: 0, late: 0, steps_done: 0, steps_total: 0}))));

  const srcBad = (D.sources || []).filter(x => x.state !== 'ok');
  const unl = D.unlinked || [];
  const footer = h('footer', {},
    h('span', {}, 'Minutes are rough: from the data where set, otherwise a default per kind of task.'),
    srcBad.length ? h('span', {}, 'Sources: ' + srcBad.map(x => x.label + ' ' + x.state + (x.as_of ? ' (' + x.as_of + ')' : '')).join(', ') + '.') : null,
    unl.length ? h('span', {title: unl.map(u => u.text + ' at ' + u.where).join('\n')}, unl.length + ' mentions have no link.') : null,
    C.source_note ? h('span', {}, C.source_note) : null);

  page.replaceChildren(header,
    h('div', {class: 'grid'}, h('div', {class: 'col c1'}, hero(), upTile, park), runTile, winTile),
    projs, footer);
  document.title = C.title || document.title;
  pickLogo();
}

function show(){
  const m = /^#p-(.+)$/.exec(location.hash || '');
  if (!m) return;
  const el = document.getElementById('p-' + decodeURIComponent(m[1]));
  if (el) { el.open = true; el.scrollIntoView({block: 'nearest'}); }
}

render();
show();
addEventListener('hashchange', show);
try { matchMedia('(prefers-color-scheme: dark)').addEventListener('change', pickLogo); } catch (e) { /* older browsers */ }
new MutationObserver(pickLogo).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
