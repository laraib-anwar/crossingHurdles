(async () => {
// 6c39e6d4-flagcheck: second pass. 109 -> 112 in every criterion, and moves the changed
// check ids between the answer lists ("no seats full for ...", "yes rule region is nord for ...").
const MOVES = [
  { clause: /no seats full for/i,            drop: ['zd-44568'],             add: ['zd-44326'] },
  { clause: /yes rule region is nord for/i,  drop: ['zd-44326', 'zd-44547'], add: ['zd-44149', 'zd-44568'] },
  { clause: /no prereq pilotui for/i,        drop: [],                       add: ['zd-44547'] },
];
const NUMS = [['\\b109\\b', '112'], ['\\b41 yes\\b', '42 yes'], ['\\b68 no\\b', '70 no']];

const sleep = ms => new Promise(r => setTimeout(r, ms));
const log = (...a) => console.log('%c[fill]', 'color:#4f6228;font-weight:bold', ...a);
const warn = (...a) => console.warn('[fill] CHECK BY HAND:', ...a);
const txt = el => (el.innerText || el.textContent || '').trim();
const page = (document.body.innerText + ' ' + document.body.textContent).replace(/\s+/g, ' ');
if (!page.includes('6c39e6d4')) { console.error('[fill] STOP: this is not task 6c39e6d4. Nothing was changed.'); return; }
const leafWith = re => [...document.querySelectorAll('body *')].filter(e => re.test(txt(e)) && ![...e.children].some(c => re.test(txt(c))));
function setVal(el, v) {
  const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  el.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
}
const headers = () => leafWith(/^Criterion \d+$/).filter(e => e.offsetParent !== null || e.getClientRects().length);
const maxCrit = () => Math.max(0, ...headers().map(h => +txt(h).split(' ')[1]));
function section(n) {
  const h = headers().find(e => txt(e) === 'Criterion ' + n); if (!h) return null;
  let el = h, best = h.parentElement;
  for (let i = 0; el && i < 10; i++, el = el.parentElement) {
    const names = new Set([...el.querySelectorAll('*')].filter(x => /^Criterion \d+$/.test(txt(x)) && !x.children.length).map(txt));
    if (names.size > 1) break;
    best = el;
  }
  return { h, box: best };
}
async function openSection(n) {
  const s = section(n); if (!s) return null;
  if (!s.box.querySelector('textarea')) { s.h.click(); await sleep(400); }
  const s2 = section(n);
  return s2 && s2.box.querySelector('textarea') ? s2 : null;
}
// rewrite the id list that follows a clause, up to the next ";" or the closing "."
function moveIds(v, m) {
  const k = v.search(m.clause); if (k < 0) return null;
  const start = k + v.slice(k).match(m.clause)[0].length;
  let end = v.indexOf(';', start); if (end < 0) end = v.length;
  let seg = v.slice(start, end), tail = '';
  const dot = seg.match(/\.\s*$/); if (dot) { tail = dot[0]; seg = seg.slice(0, -dot[0].length); }
  let ids = seg.match(/zd-\d+/g) || [];
  ids = ids.filter(i => !m.drop.includes(i));
  for (const a of m.add) if (!ids.includes(a)) ids.push(a);
  ids.sort();
  const lead = seg.match(/^\s*/)[0];
  return v.slice(0, start) + lead + ids.join(', ') + tail + v.slice(end);
}

const total = maxCrit();
const done = new Set();
let seatsCrit = null;
for (let n = 1; n <= total; n++) {
  const s = await openSection(n);
  if (!s) { warn('criterion', n, 'would not open'); continue; }
  const ta = s.box.querySelector('textarea');
  let v = ta.value, notes = [];
  for (const [src, to] of NUMS) { const re = new RegExp(src, 'g'); if (new RegExp(src).test(v)) { v = v.replace(re, to); notes.push('-> ' + to); } }
  MOVES.forEach((m, i) => {
    const r = moveIds(v, m);
    if (r !== null) { if (r !== v) notes.push('ids moved in "' + String(m.clause).slice(1, -2) + '"'); v = r; done.add(i); if (i === 0) seatsCrit = n; }
  });
  if (/section 4/i.test(v)) warn('criterion', n, 'says "section 4", consider rewording:', v);
  if (v !== ta.value) { setVal(ta, v); log('criterion', n, 'updated:', notes.join(' | ')); log('   now reads:', v); }
}
// no "no prereq pilotui for" list anywhere: add the clause to the seats-full criterion
if (!done.has(2)) {
  if (seatsCrit) {
    const s = await openSection(seatsCrit), ta = s.box.querySelector('textarea');
    const v = ta.value.replace(/\.\s*$/, '') + '; no prereq pilotui for zd-44547.';
    setVal(ta, v); log('criterion', seatsCrit, 'gained "no prereq pilotui for zd-44547":', v);
  } else warn('no "no seats full for" list found; zd-44547 now answers "no prereq pilotui" and is not covered');
}
if (!done.has(0)) warn('no criterion with "no seats full for" was found');
if (!done.has(1)) warn('no criterion with "yes rule region is nord for" was found');
log('done. Check the "now reads" lines, then click Finish update yourself. Nothing was submitted.');
})();
