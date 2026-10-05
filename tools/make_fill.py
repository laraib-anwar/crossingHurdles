"""Build a Chrome-console script that fills a Snorkel Geranium task page.

Usage: python3 tools/make_fill.py tools/specs/<task>.json [--copy]
Writes fill/<task>.js; --copy also puts it on the macOS clipboard.
The script refuses to run unless the page shows 'UID: <first 8 chars of task>'.

Spec keys (all optional except task):
  task            name used for the output file
  prompt_full     full prompt text to put in the User Prompt box
  prompt_replace  list of [old, new] pairs applied to the current prompt
  criteria_edit   {"31": {"text": "...", "weight": 3}}  weight may be null to keep it
  criteria_add    [{"text": "...", "weight": 3}]
  criteria_delete list of criterion numbers to delete (highest first is safest)
  uploads         {"input": "path/to/inputs.zip", "golden": "path/to/golden.zip"}
"""
import base64, json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

JS = r"""
(async () => {
const SPEC = __SPEC__;
const FILES = __FILES__;
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
"""


def main():
    spec_path = sys.argv[1]
    spec = json.load(open(spec_path))
    spec.setdefault("uid", spec["task"].split("-")[0])
    files = {}
    for kind, p in (spec.pop("uploads", {}) or {}).items():
        p = p if os.path.isabs(p) else os.path.join(ROOT, p)
        data = open(p, "rb").read()
        files[kind] = {"name": os.path.basename(p), "size": len(data), "b64": base64.b64encode(data).decode()}
    js = JS.replace("__SPEC__", json.dumps(spec, ensure_ascii=False)).replace("__FILES__", json.dumps(files))
    os.makedirs(os.path.join(ROOT, "fill"), exist_ok=True)
    out = os.path.join(ROOT, "fill", spec["task"] + ".js")
    open(out, "w").write(js)
    copied = ""
    if "--copy" in sys.argv:
        subprocess.run(["pbcopy"], input=js.encode(), check=True)
        copied = " and copied to the clipboard"
    print(f"wrote {out} ({len(js)} chars){copied}")


if __name__ == "__main__":
    main()
