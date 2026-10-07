(async () => {
const UID = "2774bd40";
const TEXT = "reads.csv and tariff.csv are left byte-for-byte unchanged by running trueup.py; the script opens them read-only and writes nothing back to either file.";
const WEIGHT = "3";
const sleep = ms => new Promise(r => setTimeout(r, ms));
const txt = el => (el.innerText || el.textContent || '').trim();
const set = (el, v) => { el.focus(); Object.getOwnPropertyDescriptor(el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.blur(); };
if (!document.body.textContent.includes(UID)) { console.log('STOP: not task ' + UID + '. Nothing changed.'); return; }
if ([...document.querySelectorAll('textarea')].some(t => t.value.includes('byte-for-byte unchanged'))) { console.log('OK: the unchanged-inputs criterion is already there. Nothing added.'); return; }
const leaves = re => [...document.querySelectorAll('body *')].filter(e => re.test(txt(e)) && ![...e.children].some(c => re.test(txt(c))));
const nums = () => leaves(/^Criterion \d+$/).map(h => +txt(h).split(' ')[1]);
const before = Math.max(...nums());
const add = [...document.querySelectorAll('button')].find(b => /add criterion/i.test(txt(b)));
if (!add) { console.log('PROBLEM: Add criterion button not found. Add it by hand.'); return; }
add.click(); await sleep(900);
const n = Math.max(...nums());
if (n <= before) { console.log('PROBLEM: no new criterion appeared. Add it by hand.'); return; }
const h = leaves(/^Criterion \d+$/).find(e => txt(e) === 'Criterion ' + n);
let box = h, best = h.parentElement;
for (let i = 0; box && i < 10; i++, box = box.parentElement) { const s = new Set([...box.querySelectorAll('*')].filter(x => /^Criterion \d+$/.test(txt(x)) && !x.children.length).map(txt)); if (s.size > 1) break; best = box; }
if (!best.querySelector('textarea')) { h.click(); await sleep(500); }
set(best.querySelector('textarea'), TEXT);
const w = [...best.querySelectorAll('input')].find(i => !['checkbox', 'radio', 'hidden', 'file'].includes(i.type));
if (w) set(w, WEIGHT); else console.log('PROBLEM: weight box not found, type 3 by hand');
console.log('OK: added criterion ' + n + ' (weight 3): ' + TEXT);
})();
