(async () => {
const UID = "2774bd40";
const ADD = [
  ["Running trueup.py reads.csv tariff.csv prints to stdout the same statement batch that statement_2026_09.txt holds below its opening note, line for line.", "2"],
  ["README.md has a section on where a true up goes wrong saying that spreading by the estimates moves the batch total by 338.55 dollars and pricing corrected months at the current tariff puts the true up total out by 619 dollars.", "2"],
  ["trueup.py reads and writes only local files and makes no network connection, so the meter readings stay on the machine.", "1"]
];
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
const weightBox = b => [...b.best.querySelectorAll('input')].find(i => !['checkbox', 'radio', 'hidden', 'file'].includes(i.type));
const have = new Set();
for (const n of nums()) { const b = await open(n); if (b) have.add(b.best.querySelector('textarea').value.trim()); }
ok('criteria on page before: ' + nums().length);
for (const [text, w] of ADD) {
  if (have.has(text)) { ok('already there: ' + text.slice(0, 60)); continue; }
  const top = Math.max(0, ...nums());
  const add = [...document.querySelectorAll('button')].find(b => /add criterion/i.test(txt(b)));
  if (!add) { bad('Add criterion button not found; add by hand: ' + text); continue; }
  add.click(); await sleep(900);
  const n = Math.max(...nums()); const b = n > top && await open(n);
  if (!b) { bad('new criterion did not appear; add by hand: ' + text); continue; }
  set(b.best.querySelector('textarea'), text); const wb = weightBox(b); if (wb) set(wb, w);
  ok('added #' + n + ' (weight ' + w + '): ' + text);
}
ok('criteria on page now: ' + nums().length + '. Click Clear feedback results, then Check feedback.');
})();
