(async () => {
const UID = "f97982ce";
const MAP = [["eastvale_rovers","millvale_rovers"],["ashford","portview"],["berwick","hollins"],["calder","westcott"],["denton","marlow"],["eastvale","millvale"],["fairmont","dunmore"],["granger","oakridge"],["holbrook","larkin"],["ironside","stanton"],["jasper","bayhurst"]];
const NEW_CLUBS = ["millvale_rovers","portview","hollins","westcott","marlow","millvale","dunmore","oakridge","larkin","stanton","bayhurst"];
const ADD = [
 ["If only stanton's appeal is allowed, standings_2026.txt gives the full order as westcott, oakridge, marlow, portview, millvale, hollins, stanton, dunmore, bayhurst, larkin, with bayhurst and larkin relegated.", 2],
 ["If only stanton's appeal is allowed, standings_2026.txt says hollins, stanton and dunmore finish level on 12 and level on mini table points, and goal difference in their three matches separates them, hollins +1, stanton 0, dunmore -1.", 2],
 ["standings_2026.txt says stanton's secretary is wrong that beating hollins 1 to 0 puts stanton above hollins if the appeal is allowed, because dunmore on 12 makes it a three-club tie in which that head to head is not the test.", 2],
 ["If only the protest is upheld, standings_2026.txt gives the full order as westcott, oakridge, marlow, portview, millvale, stanton, hollins, bayhurst, dunmore, larkin, with dunmore and larkin relegated.", 2],
 ["If only the protest is upheld, standings_2026.txt says the four clubs on 13 split on mini table points into marlow and portview (7) and millvale and stanton (1), marlow goes above portview on season goal difference, and millvale above stanton on season goals scored, 16 to 14.", 2],
 ["If stanton's appeal and protest both succeed and marlow's appeal is dismissed, standings_2026.txt gives the full order as westcott, oakridge, stanton, marlow, portview, millvale, hollins, bayhurst, dunmore, larkin, with dunmore and larkin relegated.", 2],
 ["If stanton's appeal and protest both succeed and marlow's appeal is dismissed, standings_2026.txt says stanton is alone in third on 15 and needs no tiebreak, and the three clubs on 13 break exactly as in the published table.", 1],
 ["If only marlow's appeal is allowed, standings_2026.txt gives the full order as westcott, oakridge, marlow, millvale, hollins, portview, dunmore, bayhurst, stanton, larkin, with stanton and larkin relegated.", 2],
 ["If only marlow's appeal is allowed, standings_2026.txt says hollins, portview and dunmore on 12 are separated by points among the three: hollins beat both of the others and portview beat dunmore.", 2],
 ["If marlow's appeal and stanton's protest are both upheld, standings_2026.txt gives the full order as westcott, oakridge, marlow, millvale, stanton, hollins, portview, bayhurst, dunmore, larkin, with dunmore and larkin relegated.", 2],
 ["If marlow's appeal and stanton's protest are both upheld, standings_2026.txt says millvale goes above stanton on season goals scored, 16 to 14, after their 3 to 3 draw left both on +1, and hollins goes above portview on their 1 to 0 meeting.", 2],
 ["If marlow's and stanton's appeals are allowed and the protest is dismissed, standings_2026.txt gives the full order as westcott, oakridge, marlow, millvale, hollins, portview, dunmore, stanton, bayhurst, larkin, with bayhurst and larkin relegated.", 2],
 ["If marlow's and stanton's appeals are allowed and the protest is dismissed, standings_2026.txt says the mini table of the four clubs on 12 gives hollins and portview 6 points and dunmore and stanton 3, and each pair is settled as a fresh group by its own meeting: hollins beat portview 1 to 0 and dunmore beat stanton 1 to 0.", 2],
 ["If all three cases succeed, standings_2026.txt gives the full order as westcott, oakridge, marlow, stanton, millvale, hollins, portview, bayhurst, dunmore, larkin, with dunmore and larkin relegated.", 2],
 ["If all three cases succeed, standings_2026.txt says marlow and stanton are level on 15 and marlow's 3 to 0 win at stanton on April 25 puts marlow third.", 2],
 ["The delivered files are named standings.py, standings_2026.txt and README.md.", 1]
];
const STDERR_OLD = /the one summary line the rules describe to stderr/i;
const STDERR_NEW = "one summary line to stderr in the form clubs=N matches=N goals=N forfeits=N sanction_points=N tied_groups=N, where tied_groups counts the tie notes printed and a fresh group formed partway through a tie counts as one more";
const sleep = ms => new Promise(r => setTimeout(r, ms));
const txt = el => (el.innerText || el.textContent || '').trim();
const set = (el, v) => { el.focus(); Object.getOwnPropertyDescriptor(el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.blur(); };
const ok = (...m) => console.log('%c[stand] OK', 'color:#2f6b2f;font-weight:bold', ...m);
const bad = (...m) => console.log('%c[stand] PROBLEM', 'color:#b00020;font-weight:bold', ...m);
if (!document.body.textContent.includes(UID)) { bad('not task ' + UID + '. Nothing changed.'); return; }
const leaves = re => [...document.querySelectorAll('body *')].filter(e => re.test(txt(e)) && ![...e.children].some(c => re.test(txt(c))));
const nums = () => leaves(/^Criterion \d+$/).map(h => +txt(h).split(' ')[1]);
const box = n => { const h = leaves(/^Criterion \d+$/).find(e => txt(e) === 'Criterion ' + n); if (!h) return null; let el = h, best = h.parentElement; for (let i = 0; el && i < 10; i++, el = el.parentElement) { const s = new Set([...el.querySelectorAll('*')].filter(x => /^Criterion \d+$/.test(txt(x)) && !x.children.length).map(txt)); if (s.size > 1) break; best = el; } return { h, best }; };
const open = async n => { let b = box(n); if (b && !b.best.querySelector('textarea')) { b.h.click(); await sleep(400); b = box(n); } return b && b.best.querySelector('textarea') ? b : null; };
const weightBox = b => [...b.best.querySelectorAll('input')].find(i => !['checkbox', 'radio', 'hidden', 'file'].includes(i.type));
const rename = s => {
  for (const [o, n] of MAP) {
    s = s.replace(new RegExp('\\b' + o + '\\b', 'g'), n);
    s = s.replace(new RegExp('\\b' + o[0].toUpperCase() + o.slice(1) + '\\b', 'g'), n[0].toUpperCase() + n.slice(1));
  }
  // tie-note style runs of club names ("portview marlow millvale:") are printed alphabetically
  const alt = NEW_CLUBS.filter(c => !c.includes('_')).join('|');
  return s.replace(new RegExp('\\b(?:' + alt + ')(?: (?:' + alt + ')\\b)+', 'g'), run => run.split(' ').sort().join(' '));
};
const prompt = [...document.querySelectorAll('textarea')].sort((x, y) => y.value.length - x.value.length)[0];
const before = nums().length;
ok('criteria on page before: ' + before);

// 1. delete the bundled panel-outcome criteria (31 to 35, only if they are about the panel cases)
const done = new Set(ADD.map(a => a[0]));
for (const n of [35, 34, 33, 32, 31]) {
  const b = await open(n); if (!b) continue;
  const v = b.best.querySelector('textarea').value;
  if (done.has(v.trim())) { ok('#' + n + ' is already one of the new split criteria; kept'); continue; }
  if (!/appeal|protest|panel|tiebreak|secretary/i.test(v)) { ok('#' + n + ' is not a panel-outcome criterion; kept: ' + v.slice(0, 80)); continue; }
  const del = [...b.best.querySelectorAll('button')].find(x => /delete section/i.test(txt(x)));
  if (!del) { bad('no Delete section on #' + n); continue; }
  console.log('[stand] deleting #' + n + ': ' + v);
  del.click(); await sleep(700);
}

// 2. rename every club in the prompt and in every remaining criterion
if (prompt) {
  let v = rename(prompt.value);
  if (STDERR_OLD.test(v)) v = v.replace(STDERR_OLD, STDERR_NEW);
  else if (!/tied_groups=N/.test(v)) bad('prompt has no "summary line the rules describe" phrase; add the stderr format by hand: ' + STDERR_NEW);
  if (v !== prompt.value) { set(prompt, v); ok('prompt updated (club names, stderr line format)'); } else ok('prompt already up to date');
} else bad('prompt box not found');
let renamed = 0;
for (const n of nums()) {
  const b = await open(n); if (!b) continue;
  const t = b.best.querySelector('textarea'); const nv = rename(t.value);
  if (nv !== t.value) { console.log('[stand] #' + n + ' OLD: ' + t.value + '\n          NEW: ' + nv); set(t, nv); renamed++; }
}
ok(renamed + ' criteria had club names updated');

// 3. add the split criteria (each once)
const have = new Set(); for (const n of nums()) { const b = await open(n); if (b) have.add(b.best.querySelector('textarea').value.trim()); }
for (const [text, w] of ADD) {
  if (have.has(text)) { ok('already there: ' + text.slice(0, 70)); continue; }
  const top = Math.max(...nums());
  const add = [...document.querySelectorAll('button')].find(b => /add criterion/i.test(txt(b)));
  if (!add) { bad('Add criterion button not found'); break; }
  add.click(); await sleep(900);
  const n = Math.max(...nums()); const b = n > top && await open(n);
  if (!b) { bad('new criterion did not appear for: ' + text); continue; }
  set(b.best.querySelector('textarea'), text); const wb = weightBox(b); if (wb) set(wb, String(w));
  ok('added #' + n + ' (weight ' + w + ')');
}

// 4. dump the finished rubric to the clipboard for the next pass
let out = 'TASK ' + UID + ' AFTER REBUILD\nPROMPT:\n' + (prompt ? prompt.value : '') + '\n\nCRITERIA:\n';
for (const n of nums()) { const b = await open(n); const t = b && b.best.querySelector('textarea'); const w = b && weightBox(b); out += n + ' | ' + (w ? w.value : '?') + ' | ' + (t ? t.value.replace(/\s+/g, ' ').trim() : '?') + '\n'; }
try { copy(out); ok('finished rubric copied to clipboard: ' + nums().length + ' criteria. Paste it into the chat.'); } catch (e) { console.log(out); }
console.log('%c[stand] done. Upload both zips, then paste the clipboard into the chat before checking feedback.', 'font-weight:bold');
})();
