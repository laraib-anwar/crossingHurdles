(async () => {
const UID = "f9657a53";
const ADD = ["In stdout and swap_report.txt, the 28 request lines run in swaps.csv order, s-201 through s-228, between the summary line and the night counts.", "2"];
const C24 = "roster.csv or swaps.csv is modified, renamed or deleted, whether by swapcheck.py when it runs or in the copies handed back with the submission.";
const sleep = ms => new Promise(r => setTimeout(r, ms));
const txt = el => (el.innerText || el.textContent || '').trim();
const set = (el, v) => { el.focus(); Object.getOwnPropertyDescriptor(el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.blur(); };
const ok = m => console.log('%c[swap] OK ' + m, 'color:#2f6b2f;font-weight:bold');
const bad = m => console.log('%c[swap] PROBLEM ' + m, 'color:#b00020;font-weight:bold');
if (!document.body.textContent.includes(UID)) { bad('not task ' + UID + '. Nothing changed.'); return; }
const leaves = re => [...document.querySelectorAll('body *')].filter(e => re.test(txt(e)) && ![...e.children].some(c => re.test(txt(c))));
const nums = () => leaves(/^Criterion \d+$/).map(h => +txt(h).split(' ')[1]);
const box = n => { const h = leaves(/^Criterion \d+$/).find(e => txt(e) === 'Criterion ' + n); if (!h) return null; let el = h, best = h.parentElement; for (let i = 0; el && i < 10; i++, el = el.parentElement) { const s = new Set([...el.querySelectorAll('*')].filter(x => /^Criterion \d+$/.test(txt(x)) && !x.children.length).map(txt)); if (s.size > 1) break; best = el; } return { h, best }; };
const open = async n => { let b = box(n); if (b && !b.best.querySelector('textarea')) { b.h.click(); await sleep(450); b = box(n); } return b && b.best.querySelector('textarea') ? b : null; };
// open every criterion once so their text can be read
for (const n of nums()) await open(n);
// 1. criterion 24: widen the input-preservation penalty, weight unchanged
const t24 = [...document.querySelectorAll('textarea')].find(t => /swapcheck\.py/i.test(t.value) && /roster\.csv/i.test(t.value) && /(writes|renames|deletes|modif)/i.test(t.value) && !/copies handed back/i.test(t.value));
if (!t24) ok('no script-only preservation penalty found (or already widened); left alone');
else { console.log('[swap] old penalty text: ' + t24.value); set(t24, C24); ok('preservation penalty widened (weight left as it is)'); }
// 2. add the queue-order criterion once
if ([...document.querySelectorAll('textarea')].some(t => t.value.includes('s-201 through s-228'))) ok('queue-order criterion already there; not added again');
else {
  const before = Math.max(...nums());
  const add = [...document.querySelectorAll('button')].find(b => /add criterion/i.test(txt(b)));
  if (!add) bad('Add criterion button not found; add it by hand');
  else {
    add.click(); await sleep(900);
    const n = Math.max(...nums());
    const b = n > before && await open(n);
    if (!b) bad('new criterion did not appear; add it by hand');
    else {
      set(b.best.querySelector('textarea'), ADD[0]);
      const w = [...b.best.querySelectorAll('input')].find(i => !['checkbox', 'radio', 'hidden', 'file'].includes(i.type));
      if (w) set(w, ADD[1]); else bad('weight box not found, type 2 by hand');
      ok('added criterion ' + n + ' (weight 2): ' + ADD[0]);
    }
  }
}
console.log('%c[swap] done. Upload swapcheck.zip, then Clear feedback results, Check feedback, Finish update.', 'font-weight:bold');
})();
