// Status page script. build.py inlines this file, page.css and the data into template.html.
// Pages: #home (also #overview and an empty hash), #inbox, #inbox/<hid>, #p-<id>, #waiting (also #people),
// #other (also #oneoffs). Unknown hashes show home.
const D = JSON.parse(document.getElementById('data').textContent);
const C = D.config || {};
const P = D.projects || [], W = D.waiting_on || [], O = D.one_offs || [];
const I = D.inbox || {items: [], snoozed: [], done_today: [], open: 0, effort: '0m'};
const ITEMS = I.items || [];
const STRIP = D.strip || {};
const CAP = (C.inbox && C.inbox.cap) || 7, HOME_N = (C.inbox && C.inbox.home_count) || 3;
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
function s(tag, attrs){ const e = document.createElementNS(SVG, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; }
function ring(pct, size){
  const sw = size >= 40 ? Math.round(size / 9) : 3, r = (size - sw) / 2, c = 2 * Math.PI * r, p = Math.max(0, Math.min(100, pct || 0));
  const g = s('svg', {class: 'ring', width: size, height: size, viewBox: `0 0 ${size} ${size}`, role: 'img', 'aria-label': p + ' percent done'});
  g.style.flex = 'none';
  g.append(s('circle', {cx: size/2, cy: size/2, r, fill: 'none', stroke: 'var(--track)', 'stroke-width': sw}));
  g.append(s('circle', {cx: size/2, cy: size/2, r, fill: 'none', stroke: 'var(--accent)', 'stroke-width': sw, 'stroke-linecap': 'round', 'stroke-dasharray': `${c * p / 100} ${c}`, transform: `rotate(-90 ${size/2} ${size/2})`}));
  if (size >= 40) { const fs = Math.round(size * .28); const t = s('text', {x: size/2, y: size/2 + fs * .36, 'text-anchor': 'middle', 'font-size': fs, 'font-weight': 700, fill: 'var(--strong)'}); t.textContent = p + '%'; g.append(t); }
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
function dueChip(d, word){ if (!d) return null; const n = days(d); return h('span', {class: 'chip' + (n != null && n < 0 ? ' late' : '')}, (word || 'Due') + ' ' + d + (when(d) ? ' (' + when(d) + ')' : '')); }
function statusKey(st){ return /risk|block/i.test(st || '') ? 'block' : /wait/i.test(st || '') ? 'wait' : 'done'; }
function statusChip(st){ if (!st) return null; return h('span', {class: 'chip'}, h('span', {class: 'dot ' + statusKey(st)}), st); }
function refNode(ref){
  if (!ref) return null; let m;
  if (C.tracker_url && /^[A-Z][A-Z0-9]+-\d+$/.test(ref)) return h('a', {href: C.tracker_url + ref, target: '_blank', rel: 'noopener'}, ref);
  if (C.github_org && (m = /^([a-z][a-z0-9-]+)\s+#?(\d+)$/.exec(ref))) return h('a', {href: `https://github.com/${C.github_org}/${m[1]}/pull/${m[2]}`, target: '_blank', rel: 'noopener'}, ref);
  return ref;
}
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

// ---------- inbox rows ----------
// Links from data open only when they are http or https; anything else shows as plain text.
const safe = u => typeof u === 'string' && /^https?:\/\//i.test(u.trim()) ? u.trim() : null;
function rowHref(it){ return safe(it.link) ? safe(it.link) : it.project_id && byId(it.project_id) ? '#p-' + it.project_id : '#inbox/' + it.hid; }
function inboxRow(it, hl){
  const ext = !!safe(it.link), n = days(it.due);
  const state = it.late ? (-n) + ' day' + (n < -1 ? 's' : '') + ' late' : it.due_today ? 'due today' : '';
  const chips = [h('span', {class: 'ch'}, it.effort)];
  if (it.late) chips.push(h('span', {class: 'ch late'}, state));
  else if (it.due_today) chips.push(h('span', {class: 'ch today'}, 'due today'));
  else if (it.due) chips.push(h('span', {class: 'ch'}, 'due ' + when(it.due)));
  else if (it.age) chips.push(h('span', {class: 'ch age', title: 'On your list since ' + (it.since || '').slice(0, 10)}, it.age));
  if (it.stale) chips.push(h('span', {class: 'ch stale', title: 'No due date and older than a week'}, 'stale'));
  if (it.who_waits) chips.push(h('span', {class: 'ch who', title: it.who_waits + ' is waiting'}, it.who_waits));
  return h('a', {class: 'irow' + (hl ? ' hl' : ''), id: 'i-' + it.hid, href: rowHref(it), target: ext ? '_blank' : null, rel: ext ? 'noopener' : null,
      title: it.why ? it.title + ' - ' + it.why : it.title},
    h('span', {class: 'idot' + (it.late ? ' late' : it.due_today ? ' today' : ''), role: 'img', 'aria-label': it.late ? 'late' : it.due_today ? 'due today' : 'open'}),
    h('span', {class: 'tt'}, it.title), h('span', {class: 'ich'}, chips), h('span', {class: 'chev', 'aria-hidden': 'true'}));
}
function bandList(items, hl){
  const out = []; let band = null;
  items.forEach(it => { if (it.band !== band) { band = it.band; out.push(h('div', {class: 'band'}, (I.bands || {})[band] || '')); } out.push(inboxRow(it, it.hid === hl)); });
  return out;
}
function totals(){ return plural(I.open || 0, 'item') + (I.open ? ', about ' + I.effort : ''); }
function sourcesLine(withMissing){
  const src = (D.sources || []).filter(x => withMissing || x.state !== 'missing');
  if (!src.length) return null;
  const word = {stale: 'stale', failing: 'failing', missing: 'not set up'};
  return h('div', {class: 'srcs'}, 'Sources', src.map(x => h('span', {class: 'src' + (x.state === 'ok' ? '' : ' bad'),
    title: x.state === 'failing' ? (x.error || 'failed') + (x.last_ok_at ? ' (last good ' + clock(x.last_ok_at) + ')' : '') : x.state === 'missing' ? 'Not set up on this machine' : x.state === 'stale' ? 'Not refreshed on schedule' : 'Up to date'},
    meta([x.label, x.as_of, word[x.state]]))));
}

// ---------- home ----------
function stripBlock(){
  const late = STRIP.late || 0, done = STRIP.done_today || 0, nm = STRIP.next_meeting;
  const dots = done ? Array.from({length: Math.min(done, 10)}, () => h('i')) : [h('i', {class: 'zero'}, '0')];
  if (done > 10) dots.push(h('i', {class: 'more'}, '+' + (done - 10)));
  const future = nm && !(Date.parse(nm.at) < Date.now());
  return h('div', {class: 'strip', role: 'group', 'aria-label': 'Today'},
    h('a', {class: 'st', href: '#inbox'}, h('span', {class: 'n'}, STRIP.need_you || 0), h('span', {class: 'l'}, 'need you')),
    h('a', {class: 'st', href: '#inbox'}, h('span', {class: 'n'}, STRIP.due_today || 0), h('span', {class: 'l'}, 'due today')),
    h('a', {class: 'st', href: '#inbox'}, h('span', {class: 'n' + (late > 0 ? ' late' : '')}, late), h('span', {class: 'l'}, 'late')),
    h('a', {class: 'st', href: '#inbox', title: 'Cleared from your inbox today', 'aria-label': done + ' cleared from your inbox today'}, h('span', {class: 'dots'}, dots), h('span', {class: 'l'}, 'done today')),
    future ? h('span', {class: 'meet'}, 'Next: ' + nm.time + ' ' + nm.title) : null);
}
function inboxCard(n){
  return h('div', {class: 'card'},
    h('div', {class: 'ihead'}, h('h2', {}, 'Inbox'), h('span', {class: 'tot'}, totals()), ITEMS.length ? h('a', {href: '#inbox'}, 'All') : null),
    ITEMS.length ? h('div', {class: 'ilist'}, ITEMS.slice(0, n).map(it => inboxRow(it, false))) : h('div', {class: 'empty'}, 'Nothing needs you right now.'));
}
function projectCard(p){
  const n = inboxOf(p.id).length, dl = p.deadline;
  return h('a', {class: 'card pc-card', href: '#p-' + p.id},
    h('div', {class: 'pc-top'}, ring(p.progress_pct, 56), h('div', {class: 'pc-name'}, p.name), badge(n)),
    (p.status || dl) ? h('div', {class: 'pc-meta'}, p.status ? h('span', {class: 'dot ' + statusKey(p.status), role: 'img', 'aria-label': p.status, title: p.status}) : null,
      !dl && p.status ? h('span', {}, p.status) : null,
      dl ? h('span', {class: 'dl' + (isLate(dl) ? ' late' : '')}, (isLate(dl) ? 'Deadline passed ' : 'Deadline ') + dl.slice(5) + ' (' + when(dl) + ')') : null) : null);
}
function homePage(){
  const people = new Set(W.map(w => w.person)).size, nudges = W.filter(w => days(w.nudge_due) != null && days(w.nudge_due) <= 0).length;
  return [
    stripBlock(),
    inboxCard(HOME_N),
    P.length ? h('div', {class: 'sect-on home-extra'}, 'Projects') : null,
    P.length ? h('div', {class: 'grid home-extra'}, P.map(projectCard)) : null,
    W.length ? h('a', {class: 'wline home-extra', href: '#waiting'}, 'Waiting on ' + plural(people, 'person').replace('persons', 'people') + ', ' + plural(nudges, 'nudge') + ' due', h('span', {class: 'chev', 'aria-hidden': 'true'})) : null,
  ];
}

// ---------- inbox page ----------
function inboxPage(hl){
  const shown = ITEMS.slice(0, CAP), rest = ITEMS.slice(CAP), sn = I.snoozed || [], done = I.done_today || [];
  const restOpen = !!hl && rest.some(i => i.hid === hl);
  return [
    h('div', {class: 'card'},
      h('div', {class: 'ihead'}, h('h2', {}, 'Inbox'), h('span', {class: 'tot'}, totals())),
      ITEMS.length ? h('div', {class: 'ilist'}, bandList(shown, hl)) : h('div', {class: 'empty'}, 'Nothing needs you right now.'),
      rest.length ? h('details', {class: 'fold', open: restOpen ? '' : null}, h('summary', {}, rest.length + ' more'), h('div', {class: 'ilist'}, bandList(rest, hl))) : null,
      sn.length ? h('details', {class: 'fold'}, h('summary', {}, sn.length + ' snoozed'), h('div', {class: 'ilist'}, sn.map(it => {
        const r = inboxRow(it, it.hid === hl); r.querySelector('.ich').prepend(h('span', {class: 'ch'}, 'until ' + it.snooze_until)); return r; }))) : null,
      done.length ? h('details', {class: 'fold'}, h('summary', {}, done.length + ' done today'), h('ul', {class: 'plain', style: 'padding:6px 0 4px'},
        done.map(d => h('li', {}, d.title, h('span', {class: 'd'}, 'Cleared ' + clock(d.at)))))) : null),
  ];
}

// ---------- project page (sections are separate so later visuals can slot in) ----------
function heroCard(p){
  const items = allItems(p), t = tally(items), n = inboxOf(p.id).length;
  return h('div', {class: 'card'}, h('div', {class: 'hero'}, ring(p.progress_pct, 92),
    h('div', {class: 't'}, h('div', {class: 'nm'}, h('h1', {}, p.name), badge(n)),
      h('div', {class: 'chips'}, statusChip(p.status), p.priority ? h('span', {class: 'chip'}, p.priority) : null, p.epic ? h('span', {class: 'chip'}, refNode(p.epic)) : null, dueChip(p.deadline, 'Deadline')))),
    items.length ? h('div', {style: 'margin-top:18px'}, sbar(t), legend(t)) : null);
}
function needsCard(p){
  const needs = p.needs_me || [], extra = inboxOf(p.id).filter(i => !i.from_needs_me);
  const body = [];
  if (needs.length) body.push(h('ul', {class: 'needs'}, needs.map(n => h('li', {},
    h('span', {class: 'dot ' + (isLate(n.due) ? 'late' : 'none'), role: 'img', 'aria-label': isLate(n.due) ? 'late' : 'open'}),
    h('span', {class: 'ask'}, safe(n.link) ? h('a', {href: safe(n.link), target: '_blank', rel: 'noopener'}, n.ask) : n.ask,
      h('span', {class: 'sub' + (isLate(n.due) ? ' late' : '')}, meta([refNode(n.ticket), n.due ? 'due ' + n.due + (when(n.due) ? ' (' + when(n.due) + ')' : '') : null])))))));
  if (extra.length) body.push(h('div', {class: 'ilist', style: needs.length ? 'margin-top:10px' : ''}, extra.map(it => inboxRow(it, false))));
  return h('div', {class: 'card'}, h('h2', {}, 'Needed from you'), body.length ? body : h('span', {style: 'color:var(--strong)'}, 'Nothing right now. This one is moving without you.'));
}
function standsCard(p){
  if (!p.summary && !p.next_milestone && !p.progress_basis) return null;
  return h('div', {class: 'card'}, h('h2', {}, 'Where it stands'), p.summary ? h('p', {class: 'sum'}, p.summary) : null,
    p.next_milestone ? h('p', {class: 'sum', style: 'margin-top:10px;color:var(--strong)'}, 'Next: ' + p.next_milestone) : null,
    p.progress_basis ? h('details', {class: 'fold basis-fold'}, h('summary', {}, 'How the percent was worked out'), h('div', {class: 'basis'}, (p.progress_pct || 0) + '%: ' + p.progress_basis)) : null);
}
function breakdownCard(p){
  const groups = p.breakdown || [];
  if (!groups.length) return null;
  return h('div', {class: 'card'}, h('div', {class: 'tools'}, h('h2', {style: 'margin:0'}, 'Full breakdown'), h('button', {type: 'button', id: 'toggle-all'}, 'Open all')),
    groups.map(g => { const gi = g.items || [], gt = tally(gi); return h('details', {class: 'grp'}, h('summary', {}, h('span', {class: 'g'}, g.group), sbar(gt), h('span', {class: 'ct'}, gt.done + ' of ' + gi.length + ' done')),
      gi.map(i => h('div', {class: 'item' + (key(i.state) === 'done' ? ' is-done' : '')}, h('span', {class: 'dot ' + key(i.state), title: LABEL[key(i.state)]}), h('span', {class: 'tx'}, i.text),
        h('span', {class: 'mt'}, meta([LABEL[key(i.state)], i.owner, refNode(i.ref), i.date]))))); }));
}
function waitsCard(p){ const waits = W.filter(w => w.project_id === p.id); return waits.length ? h('div', {class: 'card'}, h('h2', {}, 'Waiting on others'), waits.map(w => waitRow(w, true, false))) : null; }
function notesCards(p){
  const dec = p.decisions || [], rec = p.recent_progress || [];
  if (!dec.length && !rec.length) return null;
  return h('div', {class: 'two'},
    dec.length ? h('div', {class: 'card'}, h('h2', {}, 'Recent decisions'), h('ul', {class: 'plain'}, dec.map(d => h('li', {}, h('span', {class: 'd'}, d.date || ''), d.decision)))) : null,
    rec.length ? h('div', {class: 'card'}, h('h2', {}, 'Recent progress'), h('ul', {class: 'plain'}, rec.map(d => h('li', {}, h('span', {class: 'd'}, d.date || ''), d.text)))) : null);
}
function linksCard(p){ return (p.links || []).length ? h('div', {class: 'card'}, h('h2', {}, 'Links'), h('div', {class: 'chips'}, p.links.map(l => safe(l.url) ? h('a', {class: 'chip', href: safe(l.url), target: '_blank', rel: 'noopener'}, l.label) : h('span', {class: 'chip'}, l.label)))) : null; }
function projectPage(p){ return [heroCard(p), needsCard(p), standsCard(p), breakdownCard(p), waitsCard(p), notesCards(p), linksCard(p)]; }

// ---------- waiting and other items ----------
function waitRow(w, withPerson, withProject){
  const p = byId(w.project_id), n = days(w.since), nd = days(w.nudge_due), due = nd != null && nd <= 0, late = nd != null && nd < 0;
  const what = safe(w.link) ? h('a', {href: safe(w.link), target: '_blank', rel: 'noopener'}, w.what) : w.what;
  return h('div', {class: 'mini'}, h('span', {class: 'dot ' + (late ? 'late' : due ? 'none' : 'wait'), role: 'img', 'aria-label': late ? 'nudge late' : due ? 'nudge due today' : 'waiting'}),
    h('span', {class: 'tx'}, withPerson ? h('b', {}, w.person + ': ') : null, what,
      h('span', {class: 'sub'}, meta([withProject && p ? h('a', {href: '#p-' + p.id}, p.name) : null, w.where, n != null ? 'waiting ' + (-n) + ' day' + (n === -1 ? '' : 's') : (w.since ? 'since ' + w.since : null)]))),
    w.nudge_due ? h('span', {class: 'mt' + (late ? ' late' : '')}, 'nudge ' + w.nudge_due.slice(5) + (late ? ' (late)' : due ? ' (today)' : '')) : null);
}
function waitingPage(){
  const by = {}; W.forEach(w => (by[w.person] = by[w.person] || []).push(w));
  const names = Object.keys(by).sort((a, b) => by[b].length - by[a].length || a.localeCompare(b));
  const due = W.filter(w => days(w.nudge_due) != null && days(w.nudge_due) <= 0).length;
  return [
    h('div', {class: 'stats'}, h('span', {class: 's'}, h('span', {class: 'n'}, names.length), 'people'), h('span', {class: 's'}, h('span', {class: 'n'}, W.length), 'things you are waiting for'), h('span', {class: 's'}, h('span', {class: 'n'}, due), 'nudges due')),
    W.length ? h('div', {class: 'two'}, names.map(n => h('div', {class: 'card'}, h('div', {class: 'person'}, h('span', {class: 'who'}, n), h('span', {class: 'count'}, by[n].length)), by[n].map(w => waitRow(w, false, true)))))
      : h('div', {class: 'card'}, h('div', {class: 'empty'}, 'Nothing is waiting on anyone else.')),
  ];
}
function otherPage(){
  const sorted = O.slice().sort((a, b) => (key(a.state) === 'done') - (key(b.state) === 'done') || (b.needs_me ? 1 : 0) - (a.needs_me ? 1 : 0));
  return [
    h('div', {class: 'stats'}, h('span', {class: 's'}, h('span', {class: 'n'}, openOff.length), 'open items'), h('span', {class: 's'}, h('span', {class: 'n'}, offNeeds), 'need you')),
    h('div', {class: 'card'}, sbar(tally(O)), legend(tally(O))),
    h('div', {class: 'grid'}, sorted.map(o => h('div', {class: 'card', style: 'display:flex;flex-direction:column;gap:10px'},
      h('div', {class: 'pc-top'}, o.progress_pct != null ? ring(o.progress_pct, 48) : h('span', {class: 'dot ' + key(o.state), style: 'width:14px;height:14px'}), h('div', {class: 'pc-name', style: key(o.state) === 'done' ? 'color:var(--muted)' : ''}, o.title), o.needs_me && key(o.state) !== 'done' ? h('span', {class: 'badge'}, 'needs you') : null),
      h('div', {class: 'chips'}, h('span', {class: 'chip'}, h('span', {class: 'dot ' + key(o.state)}), LABEL[key(o.state)]), key(o.state) !== 'done' ? dueChip(o.due) : null, o.ref ? h('span', {class: 'chip'}, refNode(o.ref)) : null),
      o.note ? h('div', {style: 'font-size:13px'}, o.note) : null))),
  ];
}

// ---------- shell: drawer, focus, routes ----------
function navLink(hash, label, pre, pct, n){ return h('a', {href: '#' + hash, 'data-h': hash}, pre, h('span', {class: 'nm'}, label), pct != null ? h('span', {class: 'pc'}, pct + '%') : null, badge(n)); }
function setMenu(open){ $('drawer').hidden = !open; $('scrim').hidden = !open; $('menu-btn').setAttribute('aria-expanded', open ? 'true' : 'false'); if (open) { const f = $('drawer').querySelector('a'); if (f) f.focus(); } }
function setFocus(on, save){
  document.body.classList.toggle('focus', on);
  $('focus-btn').setAttribute('aria-pressed', on ? 'true' : 'false');
  if (save) store('ps-focus', on ? '1' : '0');
}
function stamp(){
  const at = D.built_at || D.as_of, el = $('asof'); if (!at) return;
  el.textContent = 'As of ' + (clock(at) || at);
  const hrs = (Date.now() - Date.parse(at)) / 36e5;
  if (hrs > 2) { el.classList.add('is-old'); el.append(h('span', {class: 'old'}, 'old snapshot, built ' + (hrs < 48 ? Math.floor(hrs) + 'h' : Math.floor(hrs / 24) + 'd') + ' ago')); }
}
function build(){
  stamp();
  document.title = (I.open > 0 ? '(' + I.open + ') ' : '') + BASE_TITLE;
  const nav = $('drawer');
  const close = h('button', {class: 'close', type: 'button', id: 'menu-close'}, 'Close');
  nav.append(close, navLink('home', 'Home'), navLink('inbox', 'Inbox', null, null, I.open || 0), navLink('waiting', 'Waiting on others'),
    O.length ? navLink('other', 'Other items', null, null, offNeeds) : null, P.length ? h('div', {class: 'lbl'}, 'Projects') : null);
  P.forEach(p => nav.append(navLink('p-' + p.id, p.name, ring(p.progress_pct, 22), p.progress_pct || 0, inboxOf(p.id).length)));
  $('menu-btn').addEventListener('click', () => setMenu($('drawer').hidden));
  $('scrim').addEventListener('click', () => setMenu(false));
  close.addEventListener('click', () => setMenu(false));
  nav.addEventListener('click', e => { if (e.target.closest && e.target.closest('a')) setMenu(false); });
  $('focus-btn').addEventListener('click', () => setFocus(!document.body.classList.contains('focus'), true));
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { if (!$('drawer').hidden) { setMenu(false); $('menu-btn').focus(); } return; }
    const t = e.target, typing = t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable);
    if ((e.key === 'f' || e.key === 'F') && !typing && !e.metaKey && !e.ctrlKey && !e.altKey) setFocus(!document.body.classList.contains('focus'), true);
  });
  document.addEventListener('click', e => { if (e.target && e.target.id === 'toggle-all') { const ds = [...document.querySelectorAll('#page details.grp')], open = ds.some(d => !d.open); ds.forEach(d => d.open = open); e.target.textContent = open ? 'Close all' : 'Open all'; } });
  setFocus(store('ps-focus') === '1', false);
  show();
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
  if (hash === 'other' && O.length) return {cur: 'other'};
  return {cur: 'home'};
}
function show(){
  const r = route(), cur = r.cur;
  const body = r.p ? projectPage(r.p) : cur === 'inbox' ? inboxPage(r.hl) : cur === 'waiting' ? waitingPage() : cur === 'other' ? otherPage() : homePage();
  $('where').textContent = r.p ? r.p.name : cur === 'inbox' ? 'Inbox' : cur === 'waiting' ? 'Waiting on others' : cur === 'other' ? 'Other items' : BASE_TITLE;
  const note = C.source_note ? C.source_note : null;
  const foot = h('div', {class: 'foot' + (cur === 'home' ? ' home-extra' : '')}, sourcesLine(cur === 'inbox'), note,
    r.p ? 'Percent done is an estimate; "How the percent was worked out" says how.' : null);
  $('page').replaceChildren(...body.flat().filter(Boolean), foot);
  document.body.dataset.page = cur === 'home' ? 'home' : 'other';
  document.querySelectorAll('#drawer a').forEach(a => a.dataset.h === (r.p ? r.cur : cur) ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current'));
  const first = document.querySelector('#page details.grp'); if (first) first.open = true;
  const target = r.hl ? document.getElementById('i-' + r.hl) : null;
  if (target) target.scrollIntoView({block: 'center'}); else window.scrollTo(0, 0);
}
addEventListener('hashchange', show);
build();
