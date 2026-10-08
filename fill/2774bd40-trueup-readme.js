(async () => {
const UID = "2774bd40";
const WORKED = "README.md works one trued-up account through by hand from its two actual readings: the span's true usage, the split by days with the spare units and tie rule, each corrected month priced under its own month's tariff against what was billed, the true up, the August charge and the amount due, ending on the same figures as that account's block in statement_2026_09.txt.";
const WRONG = "README.md explains at least two ways a true up goes wrong under billing_rules.txt, such as starting a span at the start of summer instead of the previous actual read, spreading usage by the estimates instead of by days, pricing corrected months at the current tariff, or folding the August charge into the true up, and any dollar or unit effect it quotes is consistent with the supplied data.";
const sleep = ms => new Promise(r => setTimeout(r, ms));
const txt = el => (el.innerText || el.textContent || '').trim();
const set = (el, v) => { el.focus(); Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.blur(); };
const ok = (...m) => console.log('%c[trueup] OK', 'color:#2f6b2f;font-weight:bold', ...m);
const bad = (...m) => console.log('%c[trueup] PROBLEM', 'color:#b00020;font-weight:bold', ...m);
const click = el => { for (const t of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) el.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, view: window })); };
if (!document.body.textContent.includes(UID)) { bad('not task ' + UID + '. Nothing changed.'); return; }
const leaves = re => [...document.querySelectorAll('body *')].filter(e => re.test(txt(e)) && ![...e.children].some(c => re.test(txt(c))));
const nums = () => leaves(/^Criterion \d+$/).map(h => +txt(h).split(' ')[1]);
const box = n => { const h = leaves(/^Criterion \d+$/).find(e => txt(e) === 'Criterion ' + n); if (!h) return null; let el = h, best = h.parentElement; for (let i = 0; el && i < 10; i++, el = el.parentElement) { const s = new Set([...el.querySelectorAll('*')].filter(x => /^Criterion \d+$/.test(txt(x)) && !x.children.length).map(txt)); if (s.size > 1) break; best = el; } return { h, best }; };
const open = async n => { let b = box(n); if (b && !b.best.querySelector('textarea')) { b.h.click(); await sleep(450); b = box(n); } return b && b.best.querySelector('textarea') ? b : null; };
ok('criteria on page before: ' + nums().length);
const find = async re => { for (const n of nums()) { const b = await open(n); if (b && re.test(b.best.querySelector('textarea').value)) return { n, b }; } return null; };

// 1. delete the six-of-eleven tie statistic
const tie = await find(/six of the eleven corrected spans/i);
if (!tie) ok('tie-count criterion already gone');
else {
  const del = [...tie.b.best.querySelectorAll('button')].find(x => /delete section/i.test(txt(x)));
  const before = nums().length;
  if (del) { click(del); await sleep(1000); const c = [...document.querySelectorAll('[role=dialog] button, [role=alertdialog] button')].find(x => /^(delete|confirm|yes|ok)/i.test(txt(x))); if (c) { click(c); await sleep(1000); } }
  if (nums().length < before) ok('deleted #' + tie.n + ' (six-of-eleven tie count)'); else bad('#' + tie.n + ' did not delete; click Delete section on it by hand');
}
// 2. worked account: any trued-up account, through to amount due
const w = await find(/works a-4501 by hand|works one trued-up account/i);
if (!w) bad('worked-account criterion not found; paste by hand: ' + WORKED);
else if (w.b.best.querySelector('textarea').value.trim() === WORKED) ok('#' + w.n + ' worked-account criterion already up to date');
else { console.log('[trueup] #' + w.n + ' OLD: ' + w.b.best.querySelector('textarea').value); set(w.b.best.querySelector('textarea'), WORKED); ok('#' + w.n + ' now accepts any trued-up account (weight kept)'); }
// 3. where a true up goes wrong: any correct explanation
const g = await find(/where a true up goes wrong saying|ways a true up goes wrong/i);
if (!g) bad('README pitfalls criterion not found; paste by hand: ' + WRONG);
else if (g.b.best.querySelector('textarea').value.trim() === WRONG) ok('#' + g.n + ' pitfalls criterion already up to date');
else { console.log('[trueup] #' + g.n + ' OLD: ' + g.b.best.querySelector('textarea').value); set(g.b.best.querySelector('textarea'), WRONG); ok('#' + g.n + ' now accepts any correct explanation (weight kept)'); }
ok('criteria on page now: ' + nums().length + '. Click Clear feedback results, then Check feedback.');
})();
