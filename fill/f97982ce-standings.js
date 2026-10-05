
(async () => {
const SPEC = {"task": "f97982ce-standings", "prompt_replace": [["Two cases are still with the league's disciplinary panel", "Three cases are still with the league's disciplinary panel"]], "criteria_edit": {"31": {"text": "standings_2026.txt gives, with denton's appeal dismissed, the full finishing order for the appeal-only outcome as calder, granger, denton, ashford, eastvale, berwick, ironside, fairmont, jasper, holbrook, with calder promoted and jasper and holbrook relegated, and for ironside's appeal and protest both succeeding as calder, granger, ironside, denton, ashford, eastvale, berwick, jasper, fairmont, holbrook, with calder promoted and fairmont and holbrook relegated.", "weight": null}, "32": {"text": "With denton's appeal dismissed, the protest-only order is calder, granger, denton, ashford, eastvale, ironside, berwick, jasper, fairmont, holbrook, with calder promoted and fairmont and holbrook relegated, and the note says ironside's secretary is wrong that beating berwick 1 to 0 puts ironside above berwick if the appeal is allowed, since fairmont is also on 12 and the three-club mini table puts berwick above on goal difference.", "weight": null}}, "criteria_add": [{"text": "With denton's appeal allowed, every order starts calder, granger, denton (calder promoted, bottom two relegated), then: denton alone eastvale, berwick, ashford, fairmont, jasper, ironside, holbrook; with the protest eastvale, ironside, berwick, ashford, jasper, fairmont, holbrook; with ironside's appeal eastvale, berwick, ashford, fairmont, ironside, jasper, holbrook; all three ironside, eastvale, berwick, ashford, jasper, fairmont, holbrook.", "weight": 4}]};
const FILES = {"input": {"name": "standings_inputs.zip", "size": 4415, "b64": "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"}, "golden": {"name": "standings_golden.zip", "size": 5711, "b64": "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"}};
const sleep = ms => new Promise(r => setTimeout(r, ms));
const log = (...a) => console.log('%c[fill]', 'color:#4f6228;font-weight:bold', ...a);
const warn = (...a) => console.warn('[fill] CHECK BY HAND:', ...a);
const txt = el => (el.innerText || el.textContent || '').trim();
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
  return [...document.querySelectorAll('textarea')].sort((a, b) => b.value.length - a.value.length)[0];
};
if (SPEC.prompt_full || SPEC.prompt_replace) {
  const t = promptBox();
  if (!t) warn('prompt box not found');
  else {
    let v = SPEC.prompt_full || t.value;
    for (const [a, b] of (SPEC.prompt_replace || [])) {
      if (v.includes(a)) { v = v.split(a).join(b); log('prompt: replaced', JSON.stringify(a.slice(0, 50))); }
      else if (v.includes(b)) log('prompt: already says', JSON.stringify(b.slice(0, 50)));
      else warn('prompt text not found:', a);
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
for (const n of (SPEC.criteria_delete || []).sort((a, b) => b - a)) {
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
function uploaderBox(re) {
  for (const lab of leafWith(re)) {
    let el = lab;
    for (let i = 0; el && i < 7; i++, el = el.parentElement) {
      if (el.querySelector('input[type=file]') || [...el.querySelectorAll('*')].some(x => /\.zip$/i.test(txt(x)) && !x.children.length)) return el;
    }
  }
  return null;
}
async function upload(kind, re) {
  const f = FILES[kind]; if (!f) return;
  let box = uploaderBox(re);
  if (!box) { warn(kind, 'uploader not found'); return; }
  const chips = [...box.querySelectorAll('*')].filter(x => /\.zip$/i.test(txt(x)) && !x.children.length);
  for (const chip of chips) {
    let row = chip, btns = [];
    for (let i = 0; row && i < 4 && !btns.length; i++, row = row.parentElement)
      btns = [...row.querySelectorAll('button,[role=button]')];
    const rm = btns.find(b => /remove|delete|clear|close/i.test((b.getAttribute('aria-label') || '') + (b.title || '') + txt(b))) || btns[btns.length - 1];
    if (rm) { rm.click(); await sleep(600); log(kind, ': removed', txt(chip)); } else warn(kind, ': no remove button next to', txt(chip));
  }
  box = uploaderBox(re) || box;
  const inp = box.querySelector('input[type=file]') || [...document.querySelectorAll('input[type=file]')].find(i => box.contains(i) || box.parentElement.contains(i));
  const dt = new DataTransfer(); dt.items.add(fileFrom(f));
  if (inp) {
    inp.files = dt.files;
    inp.dispatchEvent(new Event('input', { bubbles: true }));
    inp.dispatchEvent(new Event('change', { bubbles: true }));
    log(kind, ': uploaded', f.name, '(' + f.size + ' bytes)');
  } else {
    const zone = box.querySelector('[class*=drop],[class*=Drop]') || box;
    for (const t of ['dragenter', 'dragover', 'drop']) zone.dispatchEvent(new DragEvent(t, { bubbles: true, cancelable: true, dataTransfer: dt }));
    log(kind, ': dropped', f.name, 'on the uploader (no file input found)');
  }
}
await upload('input', /^Input File Uploader\s*\*?$/i);
await upload('golden', /golden.*(upload|file)|solution.*upload/i);

log('done. Check every field, then click Finish update yourself. Nothing was submitted.');
})();
