(async () => {
const ADD = {
  d995a284: { task: 'points', weight: 3, text: "points_run.py opens members.csv and activity.csv only for reading and never writes to, renames or replaces either file; its output goes to stdout and stderr." },
  f9657a53: { task: 'swapcheck', weight: 2, text: "swapcheck.py's stdout and the machine output in swap_report.txt each open with the line naming the run, swap queue worked against roster.csv, before the requests 28, applied 20, refused 8 summary line." }
};
const sleep = ms => new Promise(r => setTimeout(r, ms));
const log = (...args) => console.log('%c[fill]', 'color:#4f6228;font-weight:bold', ...args);
const warn = (...args) => console.warn('[fill] CHECK BY HAND:', ...args);
const txt = el => (el.innerText || el.textContent || '').trim();
const pageText = document.body.innerText.replace(/\s+/g, ' ');
const uid = Object.keys(ADD).find(k => pageText.includes('UID: ' + k));
if (!uid) { console.error('[fill] STOP: this page is not the points (d995a284) or swapcheck (f9657a53) task. Nothing was changed.'); return; }
const C = ADD[uid];
log('page is', C.task, '(' + uid + ')');
if ([...document.querySelectorAll('textarea')].some(t => t.value.trim() === C.text)) { log('criterion already present, nothing to add'); return; }
const leafWith = re => [...document.querySelectorAll('body *')].filter(e => re.test(txt(e)) && ![...e.children].some(c => re.test(txt(c))));
function setVal(el, v) {
  const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
  ['input', 'change'].forEach(t => el.dispatchEvent(new Event(t, { bubbles: true })));
  el.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
}
const headers = () => leafWith(/^Criterion \d+$/);
const maxCrit = () => Math.max(0, ...headers().map(h => +txt(h).split(' ')[1]));
function section(n) {
  const h = headers().find(e => txt(e) === 'Criterion ' + n); if (!h) return null;
  let el = h, best = h.parentElement;
  for (let i = 0; el && i < 10; i++, el = el.parentElement) {
    const names = new Set([...el.querySelectorAll('*')].filter(x => /^Criterion \d+$/.test(txt(x)) && !x.children.length).map(txt));
    if (names.size > 1) break; best = el;
  }
  return { h, box: best };
}
const before = maxCrit();
const add = [...document.querySelectorAll('button')].find(b => /add criterion/i.test(txt(b)));
if (!add) { warn('Add criterion button not found'); return; }
add.click(); await sleep(800);
const n = maxCrit();
if (n <= before) { warn('no new criterion appeared after clicking Add criterion'); return; }
let s = section(n);
if (s && !s.box.querySelector('textarea')) { s.h.click(); await sleep(400); s = section(n); }
if (!s || !s.box.querySelector('textarea')) { warn('criterion', n, 'would not open'); return; }
setVal(s.box.querySelector('textarea'), C.text);
const w = [...s.box.querySelectorAll('input')].find(i => !['checkbox', 'radio', 'hidden', 'file'].includes(i.type));
if (w) setVal(w, String(C.weight)); else warn('weight box for criterion', n, 'not found');
log('added criterion', n, '(weight ' + C.weight + '). Check it, then click Finish update yourself.');
})();
