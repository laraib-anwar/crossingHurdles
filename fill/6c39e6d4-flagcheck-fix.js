(async () => {
const UID = "6c39e6d4";
const NEW_CRIT = ["flagcheck.py opens flags.csv, rules.csv, users.csv and checks.csv only for reading and writes nothing back to them; its output goes to stdout and stderr.", 2];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const ok = (...args) => console.log('%c[flag] OK', 'color:#2f6b2f;font-weight:bold', ...args);
const bad = (...args) => console.log('%c[flag] PROBLEM', 'color:#b00020;font-weight:bold', ...args);
const txt = el => (el.innerText || el.textContent || '').trim();
console.log('%c[flag] started', 'font-weight:bold');
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
const critNums = () => leaves(/^Criterion \d+$/).map(h => +txt(h).split(' ')[1]);
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
  if (!s.box.querySelector('textarea')) { s.h.click(); await sleep(450); s = section(n); }
  return s && s.box.querySelector('textarea') ? s : null;
}

// 1. prompt: the deliverable is the three files, not a zip
const pt = [...document.querySelectorAll('textarea')].find(t => /one zip with everything in it/i.test(t.value));
if (!pt) ok('prompt has no "one zip with everything in it" phrase, left alone');
else {
  const before = pt.value;
  const after = before.replace(/one zip with everything in it(\s*[:,\-–]?)/i, (m, tail) => /[:,\-–]/.test(tail) ? 'these three files' + tail : 'flagcheck.py, flag_answers.txt and README.md' + tail);
  setVal(pt, after);
  const sent = (after.match(/[^.]*What I need back[^.]*\./i) || [after.slice(0, 200)])[0];
  ok('prompt sentence is now:', sent.trim());
  console.log('[flag] read that sentence once; if it reads oddly, fix the wording by hand');
}

// 2. criteria: "first readable row" -> "earliest readable row"
let changed = 0;
for (const n of critNums()) {
  const s = await opened(n); if (!s) continue;
  const ta = s.box.querySelector('textarea');
  if (/first readable row/i.test(ta.value)) {
    setVal(ta, ta.value.replace(/first readable row/gi, 'earliest readable row'));
    changed++; ok('criterion', n, 'now says "earliest readable row"');
  }
}
if (!changed) ok('no criterion said "first readable row"');

// 3. inputs-unchanged criterion, only if the prompt asks for it and no criterion already covers it
const promptText = (pt || [...document.querySelectorAll('textarea')].sort((x, y) => y.value.length - x.value.length)[0]).value;
const asks = /unchanged|as they are|exactly as|leave .{0,60}(alone|as is)|don.t (change|touch|modify)|not (be )?(changed|modified|touched)/i.test(promptText);
let covered = false;
for (const n of critNums()) { const s = section(n); const t = s && s.box.querySelector('textarea'); if (t && /(only for reading|read-only|writes nothing back|unchanged)/i.test(t.value)) covered = true; }
if (!asks) ok('prompt does not ask for unchanged inputs, no criterion added');
else if (covered) ok('a criterion already covers unchanged inputs');
else {
  const before = Math.max(...critNums());
  const add = [...document.querySelectorAll('button')].find(b => /add criterion/i.test(txt(b)));
  if (!add) bad('Add criterion button not found; add the inputs-unchanged criterion by hand');
  else {
    add.click(); await sleep(900);
    const n = Math.max(...critNums());
    if (n <= before) bad('no new criterion appeared');
    else {
      const s = await opened(n);
      setVal(s.box.querySelector('textarea'), NEW_CRIT[0]);
      const w = [...s.box.querySelectorAll('input')].find(i => !['checkbox', 'radio', 'hidden', 'file'].includes(i.type));
      if (w) setVal(w, String(NEW_CRIT[1]));
      ok('added criterion', n, '(inputs stay unchanged, weight 2)');
    }
  }
}
console.log('%c[flag] done. Upload both zips by hand, click Clear feedback results, Check feedback, then Finish update.', 'font-weight:bold');
})();
