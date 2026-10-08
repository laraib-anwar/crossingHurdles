
(async () => {
const SPEC = {"task": "6c39e6d4-flagcheck-uploads", "uid": "6c39e6d4"};
const FILES = {"input": {"name": "inputs.zip", "size": 6890, "b64": "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"}, "golden": {"name": "flagcheck.zip", "size": 5993, "b64": "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"}};
const sleep = ms => new Promise(r => setTimeout(r, ms));
const log = (...args) => console.log('%c[fill]', 'color:#4f6228;font-weight:bold', ...args);
const warn = (...args) => console.warn('[fill] CHECK BY HAND:', ...args);
const txt = el => (el.innerText || el.textContent || '').trim();
const pageText = (document.body.innerText + ' ' + document.body.textContent).replace(/\s+/g, ' ');
if (SPEC.uid && !pageText.includes(SPEC.uid)) {
  console.error('[fill] STOP: this page is not task ' + SPEC.uid + '. This script is for ' + SPEC.task + ' only. Nothing was changed.');
  return;
}
log('page matches task', SPEC.uid);
const leafWith = re => [...document.querySelectorAll('body *')].filter(e => re.test(txt(e)) && ![...e.children].some(c => re.test(txt(c))));

function setVal(el, v) {
  const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  el.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
}

// ---------- prompt ----------
const promptBox = () => {
  const lab = leafWith(/^User Prompt$/)[0];
  let el = lab;
  for (let i = 0; el && i < 6; i++, el = el.parentElement) {
    const t = el.querySelector('textarea'); if (t) return t;
  }
  return [...document.querySelectorAll('textarea')].sort((x, y) => y.value.length - x.value.length)[0];
};
if (SPEC.prompt_full || SPEC.prompt_replace) {
  const t = promptBox();
  if (!t) warn('prompt box not found');
  else {
    let v = SPEC.prompt_full || t.value;
    const pairs = SPEC.prompt_replace || [];
    for (let k = 0; k < pairs.length; k++) {
      const oldT = pairs[k][0], newT = pairs[k][1];
      if (v.includes(oldT)) { v = v.split(oldT).join(newT); log('prompt: replaced', JSON.stringify(oldT.slice(0, 50))); }
      else if (v.includes(newT)) log('prompt: already says', JSON.stringify(newT.slice(0, 50)));
      else warn('prompt text not found:', oldT);
    }
    setVal(t, v); log('prompt set,', v.length, 'chars');
  }
}

// ---------- criteria ----------
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
async function fillCrit(n, c) {
  const s = await openSection(n);
  if (!s) { warn('criterion', n, 'not found or would not open'); return; }
  setVal(s.box.querySelector('textarea'), c.text);
  if (c.weight !== null && c.weight !== undefined) {
    const w = [...s.box.querySelectorAll('input')].find(i => !['checkbox', 'radio', 'hidden', 'file'].includes(i.type));
    if (w) setVal(w, String(c.weight)); else warn('weight box for criterion', n, 'not found');
  }
  log('criterion', n, 'set', c.weight !== null && c.weight !== undefined ? '(weight ' + c.weight + ')' : '(weight kept)');
}
for (const n of (SPEC.criteria_delete || []).slice().sort((x, y) => y - x)) {
  const s = section(n);
  const btn = s && [...s.box.querySelectorAll('button')].find(b => /delete section/i.test(txt(b)));
  if (btn) { btn.click(); await sleep(500); log('criterion', n, 'deleted'); } else warn('could not delete criterion', n);
}
for (const [n, c] of Object.entries(SPEC.criteria_edit || {})) await fillCrit(+n, c);
for (const c of (SPEC.criteria_add || [])) {
  const before = maxCrit();
  const add = [...document.querySelectorAll('button')].find(b => /add criterion/i.test(txt(b)));
  if (!add) { warn('Add criterion button not found'); break; }
  add.click(); await sleep(800);
  const n = maxCrit();
  if (n <= before) { warn('no new criterion appeared after clicking Add criterion'); break; }
  await fillCrit(n, c);
}

// ---------- uploads ----------
function fileFrom(f) {
  const bin = atob(f.b64), u = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  return new File([u], f.name, { type: 'application/zip', lastModified: Date.now() });
}
const FOLLOW = Node.DOCUMENT_POSITION_FOLLOWING;
function region(re) {
  const lab = leafWith(re)[0]; if (!lab) return null;
  const ends = leafWith(/Quality Check|How many input files|^Input File Uploader|^Golden Solution File Uploader/i)
    .filter(e => e !== lab && !re.test(txt(e)) && (lab.compareDocumentPosition(e) & FOLLOW));
  const end = ends[0] || null;
  return el => (lab.compareDocumentPosition(el) & FOLLOW) && (!end || (el.compareDocumentPosition(end) & FOLLOW));
}
function clickEl(el) {
  for (const t of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'])
    el.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, view: window }));
}
async function upload(kind, re) {
  const f = FILES[kind]; if (!f) return;
  const inR = region(re);
  if (!inR) { warn(kind, 'uploader label not found'); return; }
  const chips = () => [...document.querySelectorAll('body *')].filter(x => !x.children.length && /\.zip$/i.test(txt(x)) && inR(x));
  for (const chip of chips()) {
    if (txt(chip) === f.name) continue;
    let row = chip, cands = [];
    for (let i = 0; row && i < 5 && cands.length < 2; i++, row = row.parentElement)
      cands = [...row.querySelectorAll('button,[role=button],svg')];
    const label = e => [e.getAttribute('aria-label'), e.getAttribute('title'), e.getAttribute('data-testid'), e.getAttribute('class'), txt(e)].join(' ');
    let rm = cands.find(e => /remove|delete|close|clear|trash|lucide-x|\bx\b/i.test(label(e)));
    if (!rm) rm = cands[cands.length - 1];
    if (rm) { clickEl(rm.closest('button,[role=button]') || rm); await sleep(800); }
    if (chips().some(c => c === chip && document.contains(c))) warn(kind, ': could not remove', txt(chip), '- remove it by hand');
    else log(kind, ': removed', txt(chip));
  }
  await sleep(500);
  const dt = new DataTransfer(); dt.items.add(fileFrom(f));
  const inp = [...document.querySelectorAll('input[type=file]')].find(inR);
  if (inp) {
    inp.files = dt.files;
    inp.dispatchEvent(new Event('input', { bubbles: true }));
    inp.dispatchEvent(new Event('change', { bubbles: true }));
  } else {
    const zoneText = [...document.querySelectorAll('body *')].find(x => !x.children.length && /^Upload file$/i.test(txt(x)) && inR(x));
    const zone = zoneText && (zoneText.closest('[role=presentation],[role=button],label,div'));
    if (zone) for (const t of ['dragenter', 'dragover', 'drop']) zone.dispatchEvent(new DragEvent(t, { bubbles: true, cancelable: true, dataTransfer: dt }));
  }
  await sleep(2500);
  if (chips().some(c => txt(c) === f.name)) log(kind, ': uploaded', f.name);
  else warn(kind, ': upload of', f.name, 'did not show on the page - upload it by hand');
}
await upload('input', /^Input File Uploader\s*\*?$/i);
await upload('golden', /^Golden Solution File Uploader\s*\*?$/i);

log('done. Check every field, then click Finish update yourself. Nothing was submitted.');
})();

// ---------- report only: were the 2026-10-07 rubric/prompt scripts applied? ----------
(async () => {
await new Promise(r => setTimeout(r, 9000));
const page = (document.body.innerText + ' ' + document.body.textContent).replace(/\s+/g, ' ');
if (!page.includes('6c39e6d4')) return;
const areas = [...document.querySelectorAll('textarea')].map(t => t.value);
const crit = areas.filter(v => v.length < 600);
const prompt = areas.slice().sort((x, y) => y.length - x.length)[0] || '';
const stale = [];
if (crit.some(v => /\b109\b/.test(v))) stale.push('a criterion still says 109 checks (should be 112): run fill/6c39e6d4-flagcheck-lists.js');
if (crit.some(v => /\b41 yes\b|\b68 no\b/.test(v))) stale.push('a criterion still says 41 yes / 68 no (should be 42 / 70): run fill/6c39e6d4-flagcheck-lists.js');
if (crit.some(v => /first readable row/i.test(v))) stale.push('a criterion still says "first readable row" (should be "earliest readable row"): run fill/6c39e6d4-flagcheck-fix.js');
if (/one zip/i.test(prompt)) stale.push('the prompt still asks for "one zip": run fill/6c39e6d4-flagcheck-fix.js');
if (!crit.some(v => /only for reading/i.test(v))) stale.push('no read-only-inputs criterion found: run fill/6c39e6d4-flagcheck-fix.js');
if (stale.length) stale.forEach(s => console.warn('[fill] STILL TO DO:', s));
else console.log('%c[fill] rubric and prompt already carry the 2026-10-07 changes. Click Finish update.', 'color:#4f6228;font-weight:bold');
})();
