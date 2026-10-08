(async () => {
const UID = "2774bd40";
const RUBRIC = [
 ["Running trueup.py reads.csv tariff.csv writes this line to stderr: accounts=14 august=369115 trueup=70420 corrected=11 due=439535", 5],
 ["statement_2026_09.txt opens its batch with a line naming September as the statement month, directly followed by the summary line of batch totals and then the first account block.", 1],
 ["In statement_2026_09.txt, a-3117 shows August usage 53 units and charge 29910 cents, no corrected months and no true up line, and amount due 29910 cents.", 2],
 ["In statement_2026_09.txt, a-4501 shows corrected May 44 units 21470 cents against 30 units 12300 billed, June 42 units 20160 against 28 units 11480, July 43 units 20815 against 28 units 11480, true up 27185 and amount due 49895 after an August charge of 22710.", 3],
 ["In statement_2026_09.txt, a-2933 shows corrected May 31 units 12955 cents against 56 units 29330 billed, June 30 units 12300 against 62 units 33260, July 31 units 12955 against 66 units 35880, and a true up of -60260.", 3],
 ["In statement_2026_09.txt, a-2933 shows an August charge of 13350 cents for 30 units and an amount due of -46910 cents, printed as a negative credit.", 3],
 ["In statement_2026_09.txt, a-5169 corrects only July, 40 units 18850 cents against 23 units 9430 billed, with true up 9420, August 39 units 19830 and amount due 29250.", 3],
 ["In statement_2026_09.txt, a-1846 shows corrected May 97 units 56185 cents, June 93 units 53565 and July 96 units 55530, true up 43885, August 96 units 60870 and amount due 104755.", 2],
 ["In statement_2026_09.txt, a-6220 shows June corrected to 1 unit 410 cents against 2 units 820 billed and July corrected to 2 units 820 against 0 units 0, with true up 410 and amount due 855.", 2],
 ["In statement_2026_09.txt, a-8814 shows corrected May 94 units 54220 cents, June 91 units 52255 and July 94 units 54220, true up 81220, August 94 units 59430 and amount due 140650.", 2],
 ["In statement_2026_09.txt, a-2290 corrects only June and July, 53 units 27365 cents against 49 units 24745 billed and 54 units 28020 against 50 units 25400, with true up 5240 and amount due 35870.", 2],
 ["In statement_2026_09.txt, a-6618 shows a true up of -56985 cents and an amount due of -40035 cents, printed as a negative credit.", 2],
 ["In statement_2026_09.txt, a-9035 shows August usage 32 units and charge 14790 cents with no corrected months and no true up line, and amount due 14790 cents.", 3],
 ["In statement_2026_09.txt, a-4127 corrects only June and July, 42 units 20160 cents against 38 units 17540 billed and 44 units 21470 against 41 units 19505, with true up 4585 and amount due 27295.", 2],
 ["In statement_2026_09.txt, a-5583 corrects only July, 43 units 20815 cents against 47 units 23435 billed, with true up -2620 and amount due 20090.", 2],
 ["In statement_2026_09.txt, a-3364 shows corrected May 40 units 18850 cents, June 38 units 17540 and July 40 units 18850, each against 30 units 12300 billed, with true up 18340 and amount due 38890.", 2],
 ["In statement_2026_09.txt, a-7702 shows August usage 59 units and charge 34230 cents, no true up line, and amount due 34230 cents.", 1],
 ["README.md works a-4501 by hand from its 1180 and 1352 actual readings: 172 units over 123 days, 2 spare units, the first to June on its .95 and the second to May on the tie.", 2],
 ["README.md says the tie rule decides a spare unit in six of the eleven corrected spans: a-4501, a-2933, a-5169, a-1846, a-6220 and a-4127.", 2],
 ["trueup.py takes the statement month and the August label from the read dates in reads.csv instead of printing them as fixed text.", 2],
 ["reads.csv and tariff.csv are left byte-for-byte unchanged by running trueup.py; the script opens them read-only and writes nothing back to either file.", 3],
 ["The delivered files are named trueup.py, statement_2026_09.txt and README.md.", 1],
 ["statement_2026_09.txt shows a-2933 or a-6618 with an amount due of zero instead of its negative credit.", -5],
 ["statement_2026_09.txt prices a corrected May, June or July month at the August 2026 tariff instead of the tariff in force for that month.", -5]
];
const TAIL = "Write trueup.py so it takes reads.csv and then tariff.csv on the command line, prints the statement batch to stdout, and writes one tally line to stderr in the form accounts=N august=N trueup=N corrected=N due=N, where due adds up every account's amount due. The month names on the statement should come from the read dates, not be typed in, so next month's batch runs unchanged. Keep this month's run as statement_2026_09.txt, with a few lines of your own at the top on what moved. Work one trued-up account through by hand in README.md, from its readings to its amount due, and make sure trueup.py lands on the same units and cents; the README should also say how to run it and where a true up goes wrong. trueup.py is the single deliverable that has to be right; the statement and README.md are there so billing can check the numbers and whoever runs next month's batch can pick it up. reads.csv and tariff.csv are straight exports from the billing system: leave them untouched, and keep the readings on this machine.";
const sleep = ms => new Promise(r => setTimeout(r, ms));
const txt = el => (el.innerText || el.textContent || '').trim();
const set = (el, v) => { el.focus(); Object.getOwnPropertyDescriptor(el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.blur(); };
const ok = (...m) => console.log('%c[trueup] OK', 'color:#2f6b2f;font-weight:bold', ...m);
const bad = (...m) => console.log('%c[trueup] PROBLEM', 'color:#b00020;font-weight:bold', ...m);
if (!document.body.textContent.includes(UID)) { bad('not task ' + UID + '. Nothing changed.'); return; }
const leaves = re => [...document.querySelectorAll('body *')].filter(e => re.test(txt(e)) && ![...e.children].some(c => re.test(txt(c))));
const nums = () => leaves(/^Criterion \d+$/).map(h => +txt(h).split(' ')[1]);
const box = n => { const h = leaves(/^Criterion \d+$/).find(e => txt(e) === 'Criterion ' + n); if (!h) return null; let el = h, best = h.parentElement; for (let i = 0; el && i < 10; i++, el = el.parentElement) { const s = new Set([...el.querySelectorAll('*')].filter(x => /^Criterion \d+$/.test(txt(x)) && !x.children.length).map(txt)); if (s.size > 1) break; best = el; } return { h, best }; };
const open = async n => { let b = box(n); if (b && !b.best.querySelector('textarea')) { b.h.click(); await sleep(400); b = box(n); } return b && b.best.querySelector('textarea') ? b : null; };
const weightBox = b => [...b.best.querySelectorAll('input')].find(i => !['checkbox', 'radio', 'hidden', 'file'].includes(i.type));

// 1. prompt: rewrite the close, fix any account count
const pt = [...document.querySelectorAll('textarea')].filter(t => /trueup\.py/.test(t.value)).sort((x, y) => y.value.length - x.value.length)[0];
if (!pt) bad('prompt box not found');
else {
  let v = pt.value;
  const i = Math.max(v.indexOf('Build trueup.py'), v.indexOf('Write trueup.py'));
  if (i < 0) bad('could not find "Build trueup.py" or "Write trueup.py" in the prompt; close left alone. Prompt:\n' + v);
  else { console.log('[trueup] OLD prompt close:\n' + v.slice(i)); v = v.slice(0, i) + TAIL; }
  v = v.replace(/\bsix (water )?accounts\b/gi, 'fourteen $1accounts').replace(/\b6 accounts\b/g, '14 accounts');
  if (v !== pt.value) { set(pt, v); ok('prompt updated'); } else ok('prompt already up to date');
}

// 2. overwrite criteria 1..N in place, add any missing, delete the rest
const have = nums();
ok('criteria on page before: ' + have.length + ', new rubric: ' + RUBRIC.length);
for (let k = 0; k < RUBRIC.length; k++) {
  const [text, w] = RUBRIC[k];
  let b = have.includes(k + 1) ? await open(k + 1) : null;
  if (!b) {
    const top = Math.max(0, ...nums());
    const add = [...document.querySelectorAll('button')].find(x => /add criterion/i.test(txt(x)));
    if (!add) { bad('Add criterion button not found at #' + (k + 1)); break; }
    add.click(); await sleep(900);
    const n = Math.max(...nums()); b = n > top ? await open(n) : null;
    if (!b) { bad('could not add #' + (k + 1)); continue; }
  }
  const t = b.best.querySelector('textarea');
  if (t.value.trim() !== text) { if (t.value.trim()) console.log('[trueup] #' + (k + 1) + ' OLD: ' + t.value); set(t, text); }
  const wb = weightBox(b); if (wb && wb.value !== String(w)) set(wb, String(w));
}
for (const n of nums().filter(n => n > RUBRIC.length).sort((x, y) => y - x)) {
  const b = await open(n); if (!b) continue;
  const del = [...b.best.querySelectorAll('button')].find(x => /delete section/i.test(txt(x)));
  console.log('[trueup] deleting #' + n + ': ' + b.best.querySelector('textarea').value);
  if (del) { del.click(); await sleep(700); } else bad('no Delete section on #' + n);
}
const end = nums().length;
if (end === RUBRIC.length) ok('rubric now has ' + end + ' criteria, all set'); else bad('rubric has ' + end + ' criteria, expected ' + RUBRIC.length + '; check the end of the list');
console.log('%c[trueup] done. Upload both zips, add the third O*NET task, then Clear feedback results, Check feedback, Finish update.', 'font-weight:bold');
})();
