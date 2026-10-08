(async () => {
const UID = "2774bd40";
const NEW = "statement_2026_09.txt opens its batch with a line naming September as the statement month, followed by the summary line giving 14 accounts, 369115 cents of August charges, 70420 cents of true up and 11 accounts carrying a true up, and then the first account block.";
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
for (const n of nums()) {
  const b = await open(n); if (!b) continue;
  const t = b.best.querySelector('textarea');
  if (t.value.trim() === NEW) { ok('#' + n + ' already binds the summary values'); return; }
  if (/opens its batch with a line naming September/i.test(t.value)) {
    console.log('[trueup] #' + n + ' OLD: ' + t.value);
    set(t, NEW);
    const w = [...b.best.querySelectorAll('input')].find(i => !['checkbox', 'radio', 'hidden', 'file'].includes(i.type));
    if (w) set(w, '2');
    ok('#' + n + ' now binds the four summary values (weight 2): ' + NEW);
    return;
  }
}
bad('statement-opening criterion not found. Open criterion 2 and paste by hand (weight 2): ' + NEW);
})();
