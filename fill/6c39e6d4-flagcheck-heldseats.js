(async () => {
// 6c39e6d4-flagcheck: held-seat revision. Rewrites any criterion quoting an answer line or count
// that changed, by text not by number, then adds the new criteria. Nothing is submitted.
const SWAP = [
  ['zd-44149 2026-06-04 u-abel pilotui no seats full', 'zd-44149 2026-06-04 u-abel pilotui yes rule region is nord'],
  ['zd-44326 2026-06-12 u-lars pilotui yes rule region is nord', 'zd-44326 2026-06-12 u-lars pilotui no seats full'],
  ['zd-44547 2026-06-16 u-lars pilotalerts yes rule region is nord', 'zd-44547 2026-06-16 u-lars pilotalerts no prereq pilotui'],
  ['zd-44568 2026-06-16 u-devi pilotalerts no seats full', 'zd-44568 2026-06-16 u-devi pilotalerts yes rule region is nord'],
  ['checks=109 yes=41 no=68', 'checks=112 yes=42 no=70'],
  ['rule: 38', 'rule: 39'],
  ['prereq: 11', 'prereq: 12'],
  ['seats: 12', 'seats: 13'],
];
const ADD = [
  { text: 'flag_answers.txt contains the lines "zd-45207  2026-08-06  u-vero  pilotui  yes  rule region is nord" and "zd-45231  2026-08-13  u-lars  pilotui  no  seats full".', weight: 3 },
  { text: 'flag_answers.txt contains the line "zd-44612  2026-06-22  u-lars  pilotinvite  no  seats full".', weight: 2 },
];
const LOOK = /\b109\b|\b41 yes\b|\b68 no\b|u-abel|u-lars|u-devi|u-vero|re-?dealt|pushes|bump/i;

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
const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
function swapAll(v) {
  let out = v, hits = [];
  for (const [o, n] of SWAP) {
    const re = new RegExp(o.split(' ').map(esc).join('(\\s+)'), 'g');
    out = out.replace(re, (m, sep) => { hits.push(o); return n.split(' ').join(sep || ' '); });
  }
  return { out, hits };
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

// prompt: only reported, never changed
const pl = leafWith(/^User Prompt$/)[0];
let pbox = null;
for (let el = pl, i = 0; el && i < 6 && !pbox; i++, el = el.parentElement) pbox = el.querySelector('textarea');
if (pbox && /\b109\b/.test(pbox.value)) warn('the prompt mentions 109; the batch is now 112 checks');

const total = maxCrit();
const existing = [];
const found = new Set();
for (let n = 1; n <= total; n++) {
  const s = await openSection(n);
  if (!s) { warn('criterion', n, 'would not open'); continue; }
  const ta = s.box.querySelector('textarea');
  const { out, hits } = swapAll(ta.value);
  if (hits.length) { setVal(ta, out); hits.forEach(h => found.add(h)); log('criterion', n, 'updated:', hits.join(' | ')); }
  existing.push(out.replace(/\s+/g, ' '));
  if (LOOK.test(out)) log('criterion', n, 'mentions a seat user or the old totals, read it once:', out);
}
for (const [o] of SWAP) if (!found.has(o)) log('no criterion quoted', JSON.stringify(o), '(fine if the rubric never checked it)');

for (const c of ADD) {
  const key = c.text.replace(/\s+/g, ' ');
  if (existing.some(e => e === key)) { log('already present:', c.text.slice(0, 60)); continue; }
  const before = maxCrit();
  const add = [...document.querySelectorAll('button')].find(b => /add criterion/i.test(txt(b)));
  if (!add) { warn('Add criterion button not found'); break; }
  add.click(); await sleep(800);
  const n = maxCrit();
  const s = n > before ? await openSection(n) : null;
  if (!s) { warn('new criterion did not appear'); break; }
  setVal(s.box.querySelector('textarea'), c.text);
  const w = [...s.box.querySelectorAll('input')].find(i => !['checkbox', 'radio', 'hidden', 'file'].includes(i.type));
  if (w) setVal(w, String(c.weight)); else warn('weight box for criterion', n, 'not found, set it to', c.weight);
  log('criterion', n, 'added (weight ' + c.weight + ')');
}
log('done. Upload the two new zips by hand, check the fields, then click Finish update yourself.');
})();
