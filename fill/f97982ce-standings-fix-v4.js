(async () => {
const UID = "f97982ce";
const DEL = [36, 35];
const EDIT = {
 "3": ["standings_2026.txt shows ironside with 3 points deducted, the upheld 2 point and 1 point sanctions, finishing on 10 points, and shows no deduction for fairmont because its 2 point sanction was overturned on appeal.", 2],
 "13": ["The table credits eastvale with the matches recorded under eastvale_rovers, giving eastvale p 9, w 3, d 4, l 2, gf 16, ga 15 and 13 points.", 2],
 "16": ["The table ignores the abandoned March 7 denton against ashford row and counts the April 8 replay, giving denton gf 12, ga 11 and ashford gf 10, ga 12, each with 9 matches played.", 2],
 "17": ["The table counts the April 4 calder against ironside forfeit as a 3 to 0 calder win in goals, giving calder gf 13, ga 5 and ironside ga 14.", 2],
 "18": ["The second line of standings_2026.txt's publication reads clubs 10, matches 45, goals 124, forfeits 1, sanction points 3.", 1],
 "19": ["The table, promotion line or relegation line in standings_2026.txt applies the outcome of a pending panel case instead of the records as they stand.", -4],
 "31": ["standings_2026.txt gives, with denton's appeal dismissed, the full finishing order for the appeal-only outcome as calder, granger, denton, ashford, eastvale, berwick, ironside, fairmont, jasper, holbrook, with calder promoted and jasper and holbrook relegated, and for ironside's appeal and protest both succeeding as calder, granger, ironside, denton, ashford, eastvale, berwick, jasper, fairmont, holbrook, with calder promoted and fairmont and holbrook relegated.", null],
 "32": ["With denton's appeal dismissed, the protest-only order is calder, granger, denton, ashford, eastvale, ironside, berwick, jasper, fairmont, holbrook, with calder promoted and fairmont and holbrook relegated, and the note says ironside's secretary is wrong that beating berwick 1 to 0 puts ironside above berwick if the appeal is allowed, since fairmont is also on 12 and the three-club mini table puts berwick above on goal difference.", null],
 "34": ["With denton's appeal allowed, every order starts calder, granger, denton (calder promoted, bottom two relegated), then: denton alone eastvale, berwick, ashford, fairmont, jasper, ironside, holbrook; with the protest eastvale, ironside, berwick, ashford, jasper, fairmont, holbrook; with ironside's appeal eastvale, berwick, ashford, fairmont, ironside, jasper, holbrook; all three ironside, eastvale, berwick, ashford, jasper, fairmont, holbrook.", 4]
};
const sleep = ms => new Promise(r => setTimeout(r, ms));
const ok = (...args) => console.log('%c[v4] OK', 'color:#2f6b2f;font-weight:bold', ...args);
const bad = (...args) => console.log('%c[v4] PROBLEM', 'color:#b00020;font-weight:bold', ...args);
const txt = el => (el.innerText || el.textContent || '').trim();
console.log('%c[v4] started', 'font-weight:bold');
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
  if (!s.box.querySelector('textarea')) { s.h.click(); await sleep(500); s = section(n); }
  return s && s.box.querySelector('textarea') ? s : null;
}
console.log('[v4] criteria on page before:', critNums().length, 'highest', Math.max(...critNums()));

// 1. prompt
const pt = [...document.querySelectorAll('textarea')].find(t => t.value.includes('disciplinary panel'));
const oldP = "Two cases are still with the league's disciplinary panel", newP = "Three cases are still with the league's disciplinary panel";
if (!pt) bad('prompt box not found');
else if (pt.value.includes(oldP)) { setVal(pt, pt.value.split(oldP).join(newP)); ok('prompt changed to Three cases'); }
else ok('prompt already says Three cases');

// 2. deletes, highest first, with confirm dialog handling
for (const n of DEL) {
  if (!critNums().includes(n)) { ok('criterion', n, 'already gone'); continue; }
  const s = section(n);
  const btn = s && [...s.box.querySelectorAll('button')].find(b => /delete section/i.test(txt(b)));
  if (!btn) { bad('no Delete section button for criterion', n); continue; }
  btn.click(); await sleep(700);
  const confirm = [...document.querySelectorAll('[role=dialog] button, [role=alertdialog] button, .modal button')].find(b => /^(delete|confirm|yes|ok|remove)/i.test(txt(b)));
  if (confirm) { confirm.click(); await sleep(700); }
  if (critNums().includes(n)) bad('criterion', n, 'still there after Delete section, delete it by hand');
  else ok('criterion', n, 'deleted');
}

// 3. edits
for (const [n, pair] of Object.entries(EDIT)) {
  const s = await opened(+n);
  if (!s) { bad('criterion', n, 'not found or would not open'); continue; }
  const ta = s.box.querySelector('textarea');
  setVal(ta, pair[0]);
  if (pair[1] !== null) {
    const w = [...s.box.querySelectorAll('input')].find(i => !['checkbox', 'radio', 'hidden', 'file'].includes(i.type));
    if (w) setVal(w, String(pair[1])); else bad('weight box missing for criterion', n);
  }
  await sleep(150);
  const back = (await opened(+n)).box.querySelector('textarea').value;
  if (back === pair[0]) ok('criterion', n, 'set', pair[1] === null ? '(weight kept)' : '(weight ' + pair[1] + ')');
  else bad('criterion', n, 'did not keep the new text, paste it by hand');
}

// 4. read-back summary
await sleep(800);
const nums = critNums();
console.log('[v4] criteria on page after:', nums.length, 'highest', Math.max(...nums));
const leftover = nums.filter(n => { const s = section(n); const t = s && s.box.querySelector('textarea'); return t && /WBTC|Ostrander|Kessler|Banuelos|ballot/i.test(t.value); });
if (leftover.length) bad('election text still in criteria', leftover.join(', '));
else ok('no election text left in any open criterion');
console.log('%c[v4] done. Click Clear feedback results, then Check feedback, then Finish update.', 'font-weight:bold');
})();
