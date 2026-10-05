
(async () => {
const SPEC = {"task": "f97982ce-standings", "prompt_replace": [["Two cases are still with the league's disciplinary panel", "Three cases are still with the league's disciplinary panel"]], "criteria_delete": [36, 35], "criteria_edit": {"3": {"text": "standings_2026.txt shows ironside with 3 points deducted, the upheld 2 point and 1 point sanctions, finishing on 10 points, and shows no deduction for fairmont because its 2 point sanction was overturned on appeal.", "weight": 2}, "13": {"text": "The table credits eastvale with the matches recorded under eastvale_rovers, giving eastvale p 9, w 3, d 4, l 2, gf 16, ga 15 and 13 points.", "weight": 2}, "16": {"text": "The table ignores the abandoned March 7 denton against ashford row and counts the April 8 replay, giving denton gf 12, ga 11 and ashford gf 10, ga 12, each with 9 matches played.", "weight": 2}, "17": {"text": "The table counts the April 4 calder against ironside forfeit as a 3 to 0 calder win in goals, giving calder gf 13, ga 5 and ironside ga 14.", "weight": 2}, "18": {"text": "The second line of standings_2026.txt's publication reads clubs 10, matches 45, goals 124, forfeits 1, sanction points 3.", "weight": 1}, "19": {"text": "The table, promotion line or relegation line in standings_2026.txt applies the outcome of a pending panel case instead of the records as they stand.", "weight": -4}, "31": {"text": "standings_2026.txt gives, with denton's appeal dismissed, the full finishing order for the appeal-only outcome as calder, granger, denton, ashford, eastvale, berwick, ironside, fairmont, jasper, holbrook, with calder promoted and jasper and holbrook relegated, and for ironside's appeal and protest both succeeding as calder, granger, ironside, denton, ashford, eastvale, berwick, jasper, fairmont, holbrook, with calder promoted and fairmont and holbrook relegated.", "weight": null}, "32": {"text": "With denton's appeal dismissed, the protest-only order is calder, granger, denton, ashford, eastvale, ironside, berwick, jasper, fairmont, holbrook, with calder promoted and fairmont and holbrook relegated, and the note says ironside's secretary is wrong that beating berwick 1 to 0 puts ironside above berwick if the appeal is allowed, since fairmont is also on 12 and the three-club mini table puts berwick above on goal difference.", "weight": null}, "34": {"text": "With denton's appeal allowed, every order starts calder, granger, denton (calder promoted, bottom two relegated), then: denton alone eastvale, berwick, ashford, fairmont, jasper, ironside, holbrook; with the protest eastvale, ironside, berwick, ashford, jasper, fairmont, holbrook; with ironside's appeal eastvale, berwick, ashford, fairmont, ironside, jasper, holbrook; all three ironside, eastvale, berwick, ashford, jasper, fairmont, holbrook.", "weight": 4}}, "uid": "f97982ce"};
const FILES = {"input": {"name": "standings_inputs.zip", "size": 4415, "b64": "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"}, "golden": {"name": "standings_golden.zip", "size": 5752, "b64": "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"}};
const sleep = ms => new Promise(r => setTimeout(r, ms));
const log = (...args) => console.log('%c[fill]', 'color:#4f6228;font-weight:bold', ...args);
const warn = (...args) => console.warn('[fill] CHECK BY HAND:', ...args);
const txt = el => (el.innerText || el.textContent || '').trim();
if (SPEC.uid && !document.body.innerText.includes('UID: ' + SPEC.uid)) {
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
