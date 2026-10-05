(async () => {
const UID = "f97982ce";
const EDIT = {"3": ["standings_2026.txt shows no deduction against fairmont, whose 2 point sanction for an unregistered coach was overturned on appeal, so fairmont finishes on 12 points.", 2], "17": ["The note states that holbrook's withdrawn complaint changes nothing in the published table or in any panel outcome.", 1], "18": ["The note explains that if denton's appeal is allowed the March 7 result stands as a 2 to 0 denton win and the April 8 replay drops out of every total, so denton gains 2 points and ashford loses 1.", 2]};
const sleep = ms => new Promise(r => setTimeout(r, ms));
const ok = (...args) => console.log('%c[v5] OK', 'color:#2f6b2f;font-weight:bold', ...args);
const bad = (...args) => console.log('%c[v5] PROBLEM', 'color:#b00020;font-weight:bold', ...args);
const txt = el => (el.innerText || el.textContent || '').trim();
console.log('%c[v5] started', 'font-weight:bold');
if (!document.body.textContent.includes(UID)) { bad('task id ' + UID + ' not on this page. Nothing changed.'); return; }
ok('on task', UID);
const leaves = re => [...document.querySelectorAll('body *')].filter(e => re.test(txt(e)) && ![...e.children].some(c => re.test(txt(c))));
function setVal(el, v) {
  el.focus();
  const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  el.blur();
  el.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
}
function section(n) {
  const h = leaves(/^Criterion \d+$/).find(e => txt(e) === 'Criterion ' + n); if (!h) return null;
  let el = h, best = h.parentElement;
  for (let i = 0; el && i < 10; i++, el = el.parentElement) {
    const names = new Set([...el.querySelectorAll('*')].filter(x => /^Criterion \d+$/.test(txt(x)) && !x.children.length).map(txt));
    if (names.size > 1) break;
    best = el;
  }
  return { h, box: best };
}
async function opened(n) {
  let s = section(n); if (!s) return null;
  if (!s.box.querySelector('textarea')) { s.h.click(); await sleep(500); s = section(n); }
  return s && s.box.querySelector('textarea') ? s : null;
}
for (const [n, pair] of Object.entries(EDIT)) {
  const s = await opened(+n);
  if (!s) { bad('criterion', n, 'not found or would not open'); continue; }
  setVal(s.box.querySelector('textarea'), pair[0]);
  const w = [...s.box.querySelectorAll('input')].find(i => !['checkbox', 'radio', 'hidden', 'file'].includes(i.type));
  if (w) setVal(w, String(pair[1])); else bad('weight box missing for criterion', n);
  await sleep(150);
  const back = (await opened(+n)).box.querySelector('textarea').value;
  if (back === pair[0]) ok('criterion', n, 'set (weight ' + pair[1] + ')'); else bad('criterion', n, 'did not keep the new text, paste it by hand');
}
console.log('%c[v5] done. Click Clear feedback results, then Check feedback, then Finish update.', 'font-weight:bold');
})();
