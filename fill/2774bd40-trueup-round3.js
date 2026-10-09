(async () => {
// 2774bd40-trueup, reviewer round 2026-10-08 16:36. Finds criteria by text, not number. Nothing is submitted.
const SPLITS = [["^In statement_2026_09\\.txt, a-4501 shows corrected May", [["In statement_2026_09.txt, a-4501's corrected usage is 44 units for May, 42 for June and 43 for July.", 1], ["In statement_2026_09.txt, a-4501's corrected charges are 21470 cents for May, 20160 for June and 20815 for July.", 1], ["In statement_2026_09.txt, a-4501's May, June and July were originally billed 12300, 11480 and 11480 cents.", 1], ["In statement_2026_09.txt, a-4501 shows a true up of 27185 cents, an August charge of 22710 cents for 43 units and an amount due of 49895 cents.", 2]]], ["^In statement_2026_09\\.txt, a-2933 shows corrected May", [["In statement_2026_09.txt, a-2933's corrected usage is 31 units for May, 30 for June and 31 for July.", 1], ["In statement_2026_09.txt, a-2933's corrected charges are 12955 cents for May, 12300 for June and 12955 for July.", 1], ["In statement_2026_09.txt, a-2933's May, June and July were originally billed 29330, 33260 and 35880 cents.", 1], ["In statement_2026_09.txt, a-2933 shows a true up of -60260 cents.", 1]]], ["^In statement_2026_09\\.txt, a-1846 shows corrected May", [["In statement_2026_09.txt, a-1846's corrected usage is 97 units for May, 93 for June and 96 for July.", 1], ["In statement_2026_09.txt, a-1846's corrected charges are 56185 cents for May, 53565 for June and 55530 for July.", 1], ["In statement_2026_09.txt, a-1846 shows a true up of 43885 cents, an August charge of 60870 cents for 96 units and an amount due of 104755 cents.", 1]]], ["^In statement_2026_09\\.txt, a-8814 shows corrected May", [["In statement_2026_09.txt, a-8814's corrected usage is 94 units for May, 91 for June and 94 for July.", 1], ["In statement_2026_09.txt, a-8814's corrected charges are 54220 cents for May, 52255 for June and 54220 for July.", 1], ["In statement_2026_09.txt, a-8814 shows a true up of 81220 cents, an August charge of 59430 cents for 94 units and an amount due of 140650 cents.", 1]]], ["^In statement_2026_09\\.txt, a-3364 shows corrected May", [["In statement_2026_09.txt, a-3364's corrected usage is 40 units for May, 38 for June and 40 for July.", 1], ["In statement_2026_09.txt, a-3364's corrected charges are 18850 cents for May, 17540 for June and 18850 for July.", 1], ["In statement_2026_09.txt, a-3364's May, June and July were each originally billed 30 units for 12300 cents.", 1], ["In statement_2026_09.txt, a-3364 shows a true up of 18340 cents, an August charge of 20550 cents for 40 units and an amount due of 38890 cents.", 1]]], ["^README\\.md (works|walks|takes|shows|carries)", [["README.md works one trued-up account by hand from its two actual readings to the units in each month of its span, placing the spare units by largest fraction with ties to the earlier month.", 1], ["README.md prices that account's corrected months under each month's own rates and carries the figures through the true up to an amount due that matches the account's block in statement_2026_09.txt.", 1]]]];
const EDITS = [["^In statement_2026_09\\.txt, a-2933 shows an August charge", "In statement_2026_09.txt, a-2933 shows an August charge of 13350 cents for 30 units and an amount due of -46910 cents.", null], ["^In statement_2026_09\\.txt, a-6618 shows a true up", "In statement_2026_09.txt, a-6618 shows a true up of -56985 cents and an amount due of -40035 cents.", null], ["^statement_2026_09\\.txt includes an account block for an account that does not appear in reads\\.csv", "statement_2026_09.txt raises a credit to zero: a-2933 or a-6618 shows an amount due of 0 instead of its negative amount due.", -5]];
const ADD = [["trueup.py trues up an account only when its September the 1st read has read code A; an account whose closing read is an estimate gets no true up and its August month is billed as read.", 2]];
const TAIL = "Billing wants this as trueup.py, a script they can point at next month's export and rate schedule without editing it: reads.csv first, tariff.csv second. It should print the statement batch and send one tally line to stderr as accounts=N august=N trueup=N corrected=N due=N, where due is every account's amount due added up. The batch starts with the statement month and four figures, the number of accounts, the August charges added together in cents, the true up amounts added together in cents and how many accounts carry a true up, then gives each account a block in the order it first turns up in the export: its August usage and charge, then for an account that trued up a line for each corrected month with the corrected usage and charge beside what was billed, and the true up amount, and last the amount due. Month names on the statement should come from the read dates rather than being typed in. Save September's run as statement_2026_09.txt with a few lines of your own above it on what moved this month. In README.md, say how to run it, take one trued-up account from its two actual readings to its amount due by hand so billing can see the script lands on the same units and cents, and note where a true up goes wrong. Don't change reads.csv or tariff.csv, and the readings stay on this machine.";
const FILES = {"input": {"name": "inputs.zip", "b64": "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"}, "golden": {"name": "trueup.zip", "b64": "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"}};
const sleep = ms => new Promise(r => setTimeout(r, ms));
const log = (...a) => console.log('%c[fill]', 'color:#4f6228;font-weight:bold', ...a);
const warn = (...a) => console.warn('[fill] CHECK BY HAND:', ...a);
const txt = el => (el.innerText || el.textContent || '').trim();
const pageText = (document.body.innerText + ' ' + document.body.textContent).replace(/\s+/g, ' ');
if (!pageText.includes('2774bd40')) { console.error('[fill] STOP: this is not task 2774bd40. Nothing was changed.'); return; }
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
function setCrit(s, text, weight) {
  setVal(s.box.querySelector('textarea'), text);
  if (weight !== null && weight !== undefined) {
    const w = [...s.box.querySelectorAll('input')].find(i => !['checkbox', 'radio', 'hidden', 'file'].includes(i.type));
    if (w) setVal(w, String(weight)); else warn('weight box not found for', text.slice(0, 50));
  }
}

// 1. prompt close
const lab = leafWith(/^User Prompt$/)[0];
let pt = null;
for (let el = lab, i = 0; el && i < 6 && !pt; i++, el = el.parentElement) pt = el.querySelector('textarea');
if (!pt) warn('prompt box not found');
else if (pt.value.includes(TAIL)) log('prompt close already up to date');
else {
  const v = pt.value, i = Math.max(v.indexOf('Write trueup.py'), v.indexOf('Build trueup.py'), v.indexOf('Billing wants this as trueup.py'));
  if (i < 0) warn('could not find where the prompt close starts; prompt left alone:\n' + v);
  else { log('OLD prompt close:\n' + v.slice(i)); setVal(pt, v.slice(0, i) + TAIL); log('prompt close replaced'); }
  if (/straight export/i.test(pt.value)) warn('the prompt still says "straight export" somewhere; reword that sentence');
}

// 2. criteria, by text
const total = maxCrit();
const queue = [], seen = [];
const done = { split: SPLITS.map(() => false), edit: EDITS.map(() => false) };
for (let n = 1; n <= total; n++) {
  const s = await openSection(n);
  if (!s) { warn('criterion', n, 'would not open'); continue; }
  const v = s.box.querySelector('textarea').value.trim();
  seen.push(v.replace(/\s+/g, ' '));
  SPLITS.forEach(([re, parts], k) => {
    if (!done.split[k] && new RegExp(re).test(v)) {
      log('criterion', n, 'split into', parts.length, '- old text:', v);
      setCrit(s, parts[0][0], parts[0][1]); parts.slice(1).forEach(p => queue.push(p)); done.split[k] = true;
    }
  });
  EDITS.forEach(([re, text, w], k) => {
    if (!done.edit[k] && new RegExp(re).test(v) && v !== text) { setCrit(s, text, w); done.edit[k] = true; log('criterion', n, 'rewritten:', text); }
    else if (v === text) done.edit[k] = true;
  });
}
SPLITS.forEach(([re], k) => { if (!done.split[k]) warn('no criterion matched', re, '(already split, or reworded: check by hand)'); });
EDITS.forEach(([re], k) => { if (!done.edit[k]) warn('no criterion matched', re); });
for (const a of ADD) if (!seen.includes(a[0])) queue.push(a);
for (const [text, w] of queue) {
  if (seen.includes(text)) { log('already present:', text.slice(0, 60)); continue; }
  const before = maxCrit();
  const add = [...document.querySelectorAll('button')].find(b => /add criterion/i.test(txt(b)));
  if (!add) { warn('Add criterion button not found'); break; }
  add.click(); await sleep(800);
  const n = maxCrit();
  const s = n > before ? await openSection(n) : null;
  if (!s) { warn('new criterion did not appear'); break; }
  setCrit(s, text, w); log('criterion', n, 'added (weight ' + w + ')');
}
log('criteria on page now:', maxCrit(), maxCrit() === 42 ? '(as planned)' : '(planned 42; check the warnings above)');

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
log('done. Check the prompt, the criteria and both files, then click Finish update yourself. Nothing was submitted.');
})();
