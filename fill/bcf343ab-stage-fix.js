(async () => {
const UID = "bcf343ab";
const S56 = "Stage 5 of the stage table shows Ostrander 142.0000, Kessler 124.2386, Banuelos 95.8190, Okafor 66.4095, Hargrove 81.0000, Szabo 28.0000, Wendling 28.0000, Brandt excluded and non-transferable 1.5329; stage 6 shows Ostrander 142.0000, Kessler 124.2386, Banuelos 105.8190, Okafor 83.4095, Hargrove 81.0000, Szabo 28.0000, Wendling excluded and non-transferable 2.5329.";
const S7 = "Stage 7 of the stage table shows Ostrander 142.0000, Kessler 124.2386, Banuelos 105.8190, Okafor 92.4095, Hargrove 98.0000, Szabo excluded and non-transferable 4.5329.";
const sleep = ms => new Promise(r => setTimeout(r, ms));
const txt = el => (el.innerText || el.textContent || '').trim();
const set = (el, v) => { el.focus(); Object.getOwnPropertyDescriptor(el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.blur(); };
const ok = m => console.log('%c[bcf] ' + m, 'color:#2f6b2f;font-weight:bold');
const bad = m => console.log('%c[bcf] PROBLEM ' + m, 'color:#b00020;font-weight:bold');
if (!document.body.textContent.includes(UID)) { bad('not task ' + UID + '. Nothing changed.'); return; }
const leaves = re => [...document.querySelectorAll('body *')].filter(e => re.test(txt(e)) && ![...e.children].some(c => re.test(txt(c))));
const nums = () => leaves(/^Criterion \d+$/).map(h => +txt(h).split(' ')[1]);
const box = n => { const h = leaves(/^Criterion \d+$/).find(e => txt(e) === 'Criterion ' + n); if (!h) return null; let el = h, best = h.parentElement; for (let i = 0; el && i < 10; i++, el = el.parentElement) { const s = new Set([...el.querySelectorAll('*')].filter(x => /^Criterion \d+$/.test(txt(x)) && !x.children.length).map(txt)); if (s.size > 1) break; best = el; } return { h, best }; };
const open = async n => { let b = box(n); if (b && !b.best.querySelector('textarea')) { b.h.click(); await sleep(400); b = box(n); } return b && b.best.querySelector('textarea') ? b : null; };
const weightBox = b => [...b.best.querySelectorAll('input')].find(i => !['checkbox', 'radio', 'hidden', 'file'].includes(i.type));
const all = [];
for (const n of nums()) { const b = await open(n); if (b) all.push({ n, t: b.best.querySelector('textarea'), b }); }
ok('criteria on page: ' + all.length);
let s56 = all.filter(c => c.t.value.trim() === S56);
const old = all.filter(c => c.t.value.trim() !== S56 && (/^Stages? 5 (to 7 )?of the stage table/i.test(c.t.value.trim()) || /exclude Brandt, Wendling and Szabo/i.test(c.t.value)));
if (s56.length) ok('stage 5-6 criterion already in place: #' + s56.map(c => c.n).join(', #'));
for (const c of old) {
  console.log('[bcf] #' + c.n + ' OLD: ' + c.t.value);
  if (s56.length) bad('#' + c.n + ' still has old stage 5-7 text and a stage 5-6 criterion exists; click Delete section on #' + c.n);
  else { set(c.t, S56); ok('#' + c.n + ' rewritten to the full stage 5 and stage 6 rows (weight kept)'); s56.push(c); }
}
if (!s56.length) bad('no stage 5-6 criterion found; add it by hand (weight 2): ' + S56);
const s7 = all.filter(c => /^Stage 7 of the stage table/i.test(c.t.value.trim()));
if (s7.length > 1) bad('stage 7 appears ' + s7.length + ' times (#' + s7.map(c => c.n).join(', #') + '); delete the extra one');
else if (s7.length === 1) { if (s7[0].t.value.trim() !== S7) { console.log('[bcf] #' + s7[0].n + ' OLD: ' + s7[0].t.value); set(s7[0].t, S7); ok('#' + s7[0].n + ' stage 7 completed (weight kept)'); } else ok('stage 7 criterion in place: #' + s7[0].n); }
else {
  const before = Math.max(...nums());
  const add = [...document.querySelectorAll('button')].find(b => /add criterion/i.test(txt(b)));
  if (!add) bad('no stage 7 criterion and no Add criterion button; add by hand (weight 2): ' + S7);
  else { add.click(); await sleep(900); const n = Math.max(...nums()); const b = n > before && await open(n);
    if (!b) bad('new criterion did not appear; add stage 7 by hand (weight 2)');
    else { set(b.best.querySelector('textarea'), S7); const w = weightBox(b); if (w) set(w, '2'); ok('added stage 7 as #' + n + ' (weight 2)'); } }
}
ok('criteria on page now: ' + nums().length + '. Click Clear feedback results, then Check feedback.');
})();
