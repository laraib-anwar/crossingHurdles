(async () => {
const UID = "2774bd40";
const KEEP = 23;
const EDIT = {
  21: { expect: /byte-for-byte unchanged|modified, renamed or deleted/i, text: "reads.csv or tariff.csv is modified, renamed or deleted, whether by trueup.py when it runs or in the copies handed back with the submission.", w: "-5" },
  23: { expect: /amount due of zero|account that does not appear/i, text: "statement_2026_09.txt includes an account block for an account that does not appear in reads.csv.", w: "-5" }
};
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
const click = el => { for (const t of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) el.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, view: window })); };

ok('criteria on page before: ' + nums().length);
// 1. delete everything after 23, highest first, confirming any dialog and checking it really went
for (let pass = 0; pass < 3 && Math.max(0, ...nums()) > KEEP; pass++) {
  for (const n of nums().filter(n => n > KEEP).sort((x, y) => y - x)) {
    const b = await open(n); if (!b) continue;
    const v = b.best.querySelector('textarea').value;
    const del = [...b.best.querySelectorAll('button')].find(x => /delete section/i.test(txt(x)));
    if (!del) { bad('no Delete section button on #' + n); continue; }
    const before = nums().length;
    click(del); await sleep(1000);
    const confirm = [...document.querySelectorAll('[role=dialog] button, [role=alertdialog] button, .modal button')].find(x => /^(delete|confirm|yes|ok|remove)/i.test(txt(x)));
    if (confirm) { click(confirm); await sleep(1000); }
    if (nums().length < before) ok('deleted #' + n + ': ' + v.slice(0, 70)); else bad('#' + n + ' did not delete on pass ' + (pass + 1));
  }
}
// 2. the two negatives
for (const [n, e] of Object.entries(EDIT)) {
  const b = await open(+n); if (!b) { bad('criterion ' + n + ' not found'); continue; }
  const t = b.best.querySelector('textarea');
  if (!e.expect.test(t.value)) { bad('#' + n + ' is not the expected criterion, left alone: ' + t.value); continue; }
  if (t.value.trim() !== e.text) { console.log('[trueup] #' + n + ' OLD: ' + t.value); set(t, e.text); }
  const w = weightBox(b); if (w && w.value !== e.w) set(w, e.w);
  ok('#' + n + ' now: ' + e.text + ' (weight ' + e.w + ')');
}
const end = nums().length;
if (end === KEEP) ok('rubric now has 23 criteria. Click Clear feedback results, then Check feedback.');
else bad('rubric has ' + end + ' criteria; delete everything after Criterion 23 by hand (click Delete section on each, starting from the last).');
})();
