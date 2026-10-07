(async () => {
const UID = "2774bd40";
const TAIL = "Write trueup.py so it takes reads.csv and then tariff.csv on the command line, prints the statement batch to stdout and writes the one-line tally from billing_rules.txt to stderr. Keep this month's run as statement_2026_09.txt, with a few lines of your own at the top on what moved in this batch. Before you hand it over, take one account that trued up through its span by hand and make sure trueup.py lands on the same units and cents. trueup.py is the single deliverable that has to be right; the statement and a short README.md on how to run it and where a true up goes wrong are there so billing can check the numbers and whoever runs next month's batch can pick it up. reads.csv and tariff.csv are straight exports from the billing system: leave them untouched, and keep the readings on this machine.";
const NEWCRIT = ["Below the opening note, the statement in stdout and statement_2026_09.txt starts with a line naming September as the statement month, followed by the summary line giving 6 accounts, 147115 cents for August, 20640 cents of true up and 5 accounts corrected.", "2"];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const txt = el => (el.innerText || el.textContent || '').trim();
const set = (el, v) => { el.focus(); Object.getOwnPropertyDescriptor(el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.blur(); };
const ok = (...m) => console.log('%c[trueup] OK', 'color:#2f6b2f;font-weight:bold', ...m);
const bad = (...m) => console.log('%c[trueup] PROBLEM', 'color:#b00020;font-weight:bold', ...m);
if (!document.body.textContent.includes(UID)) { bad('not task ' + UID + '. Nothing changed.'); return; }
const leaves = re => [...document.querySelectorAll('body *')].filter(e => re.test(txt(e)) && ![...e.children].some(c => re.test(txt(c))));
const nums = () => leaves(/^Criterion \d+$/).map(h => +txt(h).split(' ')[1]);
const box = n => { const h = leaves(/^Criterion \d+$/).find(e => txt(e) === 'Criterion ' + n); if (!h) return null; let el = h, best = h.parentElement; for (let i = 0; el && i < 10; i++, el = el.parentElement) { const s = new Set([...el.querySelectorAll('*')].filter(x => /^Criterion \d+$/.test(txt(x)) && !x.children.length).map(txt)); if (s.size > 1) break; best = el; } return { h, best }; };
const open = async n => { let b = box(n); if (b && !b.best.querySelector('textarea')) { b.h.click(); await sleep(450); b = box(n); } return b && b.best.querySelector('textarea') ? b : null; };

// 1. prompt: rewrite everything from "Build trueup.py" on
const pt = [...document.querySelectorAll('textarea')].find(t => /trueup\.py/.test(t.value) && t.value.length > 600);
if (!pt) bad('prompt box not found');
else if (pt.value.includes('Write trueup.py so it takes reads.csv')) ok('prompt tail already rewritten');
else {
  const i = pt.value.indexOf('Build trueup.py');
  if (i < 0) bad('"Build trueup.py" not found in the prompt; prompt left alone. Current prompt:\n' + pt.value);
  else { console.log('[trueup] OLD prompt tail:\n' + pt.value.slice(i)); set(pt, pt.value.slice(0, i) + TAIL); ok('prompt tail rewritten:\n' + TAIL); }
}

// 2. criteria 4, 7, 8, 21: values only, no quoted line format
const vals = s => s
  .replace(/["“”'`]*(\d{4}-\d{2}) corrected to\s+(\d+) units\s+(-?\d+), billed\s+(\d+) units\s+(-?\d+)["“”'`]*/g, '$1 corrected to $2 units and $3 cents against $4 units and $5 cents billed')
  .replace(/["“”'`]*august\s+(\d+) units\s+(-?\d+)(\s+corrected from the span)?["“”'`]*/gi, 'August usage $1 units and charge $2 cents')
  .replace(/["“”'`]*true up\s+(-?\d+)["“”'`]*/gi, 'true up amount $1 cents')
  .replace(/["“”'`]*due\s+(-?\d+)["“”'`]*/gi, 'amount due $1 cents')
  .replace(/\b(contains|prints|shows) (the|these) (exact )?lines?:?\s*/gi, 'gives ')
  .replace(/\s{2,}/g, ' ').trim();
for (const n of [4, 7, 8, 21]) {
  const b = await open(n);
  if (!b) { bad('criterion', n, 'would not open'); continue; }
  const t = b.best.querySelector('textarea'), v = t.value;
  if (!/corrected to|august\s+\d+ units|true up\s+-?\d+|due\s+-?\d+/i.test(v)) { ok('criterion', n, 'has no quoted statement lines, left alone:', v); continue; }
  const nv = vals(v);
  if (nv === v) { ok('criterion', n, 'already values only'); continue; }
  console.log('[trueup] criterion ' + n + ' OLD: ' + v);
  set(t, nv); ok('criterion ' + n + ' NEW (weight kept): ' + nv);
}

// 3. add the opening-lines criterion once
if ([...document.querySelectorAll('textarea')].some(t => t.value.includes('naming September as the statement month'))) ok('opening-lines criterion already there');
else {
  const before = Math.max(...nums());
  const add = [...document.querySelectorAll('button')].find(b => /add criterion/i.test(txt(b)));
  if (!add) bad('Add criterion button not found; add it by hand');
  else {
    add.click(); await sleep(900);
    const n = Math.max(...nums());
    const b = n > before && await open(n);
    if (!b) bad('new criterion did not appear; add it by hand');
    else { set(b.best.querySelector('textarea'), NEWCRIT[0]); const w = [...b.best.querySelectorAll('input')].find(i => !['checkbox', 'radio', 'hidden', 'file'].includes(i.type)); if (w) set(w, NEWCRIT[1]); ok('added criterion ' + n + ' (weight 2)'); }
  }
}
console.log('%c[trueup] done. Read the NEW lines above, upload both zips, add the third O*NET task, then Clear feedback results, Check feedback, Finish update.', 'font-weight:bold');
})();
