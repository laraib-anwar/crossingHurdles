(async () => {
const UID = "bcf343ab";
const EDITS = [
  { re: /^The certification treats Kessler's exchange area as Carlow Ridge/i, text: "The certification treats Kessler's exchange area as Carlow Ridge under the Committee's 19 September finding, not Oakmere.", w: "2" },
  { re: /^The certification denies both of Banuelos's points/i, text: "The certification denies Banuelos's first point, that Kessler should count as an Oakmere resident, citing Section 4.3's test of residence at the close of nominations.", w: "2" },
  { re: /^The certification includes a short reply addressed to Luis Banuelos/i, text: "The certification includes a short reply addressed to Luis Banuelos that answers his challenge on Kessler's exchange area.", w: "1" }
];
const ADDS = [
  ["The certification excludes Banuelos at stage 9 under Section 4.3, as the remaining Carlow Ridge candidate once Kessler is elected, before any surplus is transferred.", "2"],
  ["The certification denies Banuelos's second point, that ballots ranking him below blank positions should count for him, citing Rule 5's rule that two skipped positions in a row end a ballot.", "2"],
  ["The reply to Luis Banuelos answers his point about ballots that ranked him below blank positions.", "1"]
];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const txt = el => (el.innerText || el.textContent || '').trim();
const set = (el, v) => { el.focus(); Object.getOwnPropertyDescriptor(el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.blur(); };
const ok = (...m) => console.log('%c[bcf] OK', 'color:#2f6b2f;font-weight:bold', ...m);
const bad = (...m) => console.log('%c[bcf] PROBLEM', 'color:#b00020;font-weight:bold', ...m);
if (!document.body.textContent.includes(UID)) { bad('not task ' + UID + '. Nothing changed.'); return; }
const leaves = re => [...document.querySelectorAll('body *')].filter(e => re.test(txt(e)) && ![...e.children].some(c => re.test(txt(c))));
const nums = () => leaves(/^Criterion \d+$/).map(h => +txt(h).split(' ')[1]);
const box = n => { const h = leaves(/^Criterion \d+$/).find(e => txt(e) === 'Criterion ' + n); if (!h) return null; let el = h, best = h.parentElement; for (let i = 0; el && i < 10; i++, el = el.parentElement) { const s = new Set([...el.querySelectorAll('*')].filter(x => /^Criterion \d+$/.test(txt(x)) && !x.children.length).map(txt)); if (s.size > 1) break; best = el; } return { h, best }; };
const open = async n => { let b = box(n); if (b && !b.best.querySelector('textarea')) { b.h.click(); await sleep(450); b = box(n); } return b && b.best.querySelector('textarea') ? b : null; };
const weightBox = b => [...b.best.querySelectorAll('input')].find(i => !['checkbox', 'radio', 'hidden', 'file'].includes(i.type));
ok('criteria on page before: ' + nums().length);
const all = [];
for (const n of nums()) { const b = await open(n); if (b) all.push({ n, b, t: b.best.querySelector('textarea') }); }
const have = new Set(all.map(c => c.t.value.trim()));
// 1. edit the three bundled criteria in place
for (const e of EDITS) {
  if (have.has(e.text)) { ok('already split: ' + e.text.slice(0, 60)); continue; }
  const c = all.find(c => e.re.test(c.t.value.trim()));
  if (!c) { bad('not found, paste by hand: ' + e.text); continue; }
  console.log('[bcf] #' + c.n + ' OLD: ' + c.t.value);
  set(c.t, e.text); const w = weightBox(c.b); if (w) set(w, e.w);
  ok('#' + c.n + ' NEW (weight ' + e.w + '): ' + e.text);
}
// 2. add the split-off halves
for (const [text, w] of ADDS) {
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
// 3. "How many input files are tied to your prompt?" -> 5
const lab = leaves(/How many input files are tied to your prompt/i)[0];
let field = null;
for (let el = lab, i = 0; el && i < 6 && !field; i++, el = el.parentElement) field = el.querySelector('input:not([type=checkbox]):not([type=radio]):not([type=file]), textarea');
if (field) { if (field.value !== '5') { set(field, '5'); ok('input file count set from ' + JSON.stringify(field.value) + ' to 5'); } else ok('input file count already 5'); }
else bad('input file count box not found; type 5 by hand');
ok('criteria on page now: ' + nums().length + '. Add the third O*NET task by hand, then Clear feedback results, Check feedback, Finish update.');
})();
