(async () => {
const UID = "e129acca";
const T = {
  promo: "Run as of 2026-04-20, access_check.py reports t-1060 larch_bay sku-mirrorbay as access VIA_PROMO.",
  settle: "access_check.py settles a refund or chargeback against the newest purchase of the same sku dated on or before it, taking the purchase listed last in transactions.csv when two share that date.",
  afterClose: ["access_check.py leaves a refund or chargeback dated after an account transferred out with the closed account, so it does not kill a purchase that had already moved on with the history.", 2],
  header: ["decisions.txt and stdout open with a header line naming the as of date, 2026-07-20, before the first ticket line.", 1],
  spotAug: "Run as of 2026-08-10, access_check.py reports t-1044 holt_marsh sku-peregrine2 as access OWNED.",
  spotJun: "Run as of 2026-06-01, access_check.py reports t-1046 mill_bank sku-thicket as no access NO_GRANT and t-1047 orchid_way sku-harvest as access OWNED.",
  neg1: ["decisions.txt answers access for t-1043, whose account argos_lane sits inside the argos_lane and wick_field transfer ring.", -5],
  neg2: ["The deliverable modifies, renames or deletes catalog.csv, transactions.csv, subscriptions.csv or queries.csv.", -4]
};
const sleep = ms => new Promise(r => setTimeout(r, ms));
const txt = el => (el.innerText || el.textContent || '').trim();
const set = (el, v) => { el.focus(); Object.getOwnPropertyDescriptor(el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, 'value').set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.blur(); };
const ok = (...m) => console.log('%c[access] OK', 'color:#2f6b2f;font-weight:bold', ...m);
const bad = (...m) => console.log('%c[access] PROBLEM', 'color:#b00020;font-weight:bold', ...m);
if (!document.body.textContent.includes(UID)) { bad('not task ' + UID + '. Nothing changed.'); return; }
const leaves = re => [...document.querySelectorAll('body *')].filter(e => re.test(txt(e)) && ![...e.children].some(c => re.test(txt(c))));
const nums = () => leaves(/^Criterion \d+$/).map(h => +txt(h).split(' ')[1]);
const box = n => { const h = leaves(/^Criterion \d+$/).find(e => txt(e) === 'Criterion ' + n); if (!h) return null; let el = h, best = h.parentElement; for (let i = 0; el && i < 10; i++, el = el.parentElement) { const s = new Set([...el.querySelectorAll('*')].filter(x => /^Criterion \d+$/.test(txt(x)) && !x.children.length).map(txt)); if (s.size > 1) break; best = el; } return { h, best }; };
const open = async n => { let b = box(n); if (b && !b.best.querySelector('textarea')) { b.h.click(); await sleep(400); b = box(n); } return b && b.best.querySelector('textarea') ? b : null; };
const weightBox = b => [...b.best.querySelectorAll('input')].find(i => !['checkbox', 'radio', 'hidden', 'file'].includes(i.type));
async function readAll() { const out = []; for (const n of nums()) { const b = await open(n); if (b) out.push({ n, t: b.best.querySelector('textarea'), w: weightBox(b) }); } return out; }
async function addCrit(text, weight) {
  const before = Math.max(...nums());
  const add = [...document.querySelectorAll('button')].find(b => /add criterion/i.test(txt(b)));
  if (!add) { bad('Add criterion button not found; add by hand: ' + text); return; }
  add.click(); await sleep(900);
  const n = Math.max(...nums()); const b = n > before && await open(n);
  if (!b) { bad('new criterion did not appear; add by hand: ' + text); return; }
  set(b.best.querySelector('textarea'), text); const w = weightBox(b); if (w) set(w, String(weight)); else bad('weight box missing on ' + n);
  ok('added criterion ' + n + ' (weight ' + weight + '): ' + text);
}
const edit = (c, nv, why) => { if (c.t.value.trim() === nv) { ok('#' + c.n + ' already up to date (' + why + ')'); return; } console.log('[access] #' + c.n + ' OLD: ' + c.t.value); set(c.t, nv); ok('#' + c.n + ' NEW (' + why + ', weight kept): ' + nv); };

let all = await readAll();
ok('criteria on page: ' + all.length);

// 1. the two criteria the golden check flagged as flaky
const promo = all.find(c => /t-1060/.test(c.t.value) && /2026-04-20/.test(c.t.value));
if (promo) edit(promo, T.promo, 'flaky t-1060 criterion, rationale removed'); else bad('t-1060 / 2026-04-20 criterion not found');
const settle = all.find(c => /settles each refund or chargeback/i.test(c.t.value) || (c.t.value.trim() === T.settle));
if (settle) edit(settle, T.settle, 'flaky settle criterion, post-closure part split out'); else bad('"settles each refund or chargeback" criterion not found');

// 2. criteria 28 and 29: spot checks embedded in decisions.txt -> standalone reruns
for (const n of [28, 29]) {
  const c = all.find(x => x.n === n); if (!c) { bad('criterion ' + n + ' not found'); continue; }
  const v = c.t.value;
  if (v === T.spotAug || v === T.spotJun) { ok('#' + n + ' already a standalone rerun check'); continue; }
  if (!/decisions\.txt/i.test(v)) { ok('#' + n + ' does not mention decisions.txt, left alone: ' + v); continue; }
  if (/2026-08-10|t-1044/.test(v)) edit(c, T.spotAug, 'spot check as a rerun');
  else if (/2026-06-01|t-1046|t-1047/.test(v)) edit(c, T.spotJun, 'spot check as a rerun');
  else bad('#' + n + ' mentions decisions.txt but not a known spot check; send me its text: ' + v);
}

// 3. new positive criteria, once each
if (!all.some(c => c.t.value.includes('dated after an account transferred out'))) await addCrit(...T.afterClose); else ok('post-closure criterion already there');
if (!all.some(c => /header line/i.test(c.t.value))) await addCrit(...T.header); else ok('a header-line criterion already exists');

// 4. negatives up to at least 20 percent of positive weight
all = await readAll();
const wsum = sign => all.reduce((s, c) => { const w = parseFloat(c.w && c.w.value); return s + (isFinite(w) && Math.sign(w) === sign ? Math.abs(w) : 0); }, 0);
let pos = wsum(1), neg = wsum(-1);
ok('weights now: positive ' + pos + ', negative ' + neg + ' (' + (100 * neg / pos).toFixed(1) + '%)');
const has = re => all.some(c => re.test(c.t.value));
if (neg < 0.2 * pos && !has(/t-1043/)) { await addCrit(...T.neg1); neg += 5; }
if (neg < 0.2 * pos && !has(/renam|unchanged|read-only|only for reading/i)) { await addCrit(...T.neg2); neg += 4; }
if (neg < 0.2 * pos) bad('negative weight still ' + neg + ' of ' + pos + ' (' + (100 * neg / pos).toFixed(1) + '%); send me a screenshot');
else ok('negative weight ' + neg + ' of ' + pos + ' = ' + (100 * neg / pos).toFixed(1) + '%, at or above 20%');
ok('criteria on page now: ' + nums().length);
console.log('%c[access] done. Upload both zips, then Clear feedback results, Check feedback, Finish update.', 'font-weight:bold');
})();
