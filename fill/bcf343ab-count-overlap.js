(async () => {
// bcf343ab-count: rubric non-overlap fix. Finds criteria by their text, not their number.
// deletes: the two whole-table criteria and "Candidates are excluded in this order"
// edits:   stage 2, stages 3-4, stages 5-6 (weights kept)
// adds:    stage 7 (weight 2)
const NEW = {
  s2: "Stage 2 of the stage table transfers Ostrander's 4.0000 surplus, leaving Ostrander 142.0000, Kessler 112.2386, Banuelos 95.8190, Okafor 66.4095, Hargrove 63.0000, Wendling 22.0000, Brandt 21.0000, Szabo 19.0000, Tremblay 15.0000, Pyle 10.0000 and non-transferable 0.5329.",
  s34: "Stage 3 of the stage table shows Ostrander 142.0000, Kessler 112.2386, Banuelos 95.8190, Okafor 66.4095, Hargrove 63.0000, Szabo 26.0000, Wendling 23.0000, Brandt 23.0000, Tremblay 15.0000, Pyle excluded and non-transferable 0.5329; stage 4 shows Ostrander 142.0000, Kessler 112.2386, Banuelos 95.8190, Okafor 66.4095, Hargrove 65.0000, Szabo, Wendling and Brandt 28.0000 each, Tremblay excluded and non-transferable 1.5329.",
  s56: "Stage 5 of the stage table shows Ostrander 142.0000, Kessler 124.2386, Banuelos 95.8190, Okafor 66.4095, Hargrove 81.0000, Szabo 28.0000, Wendling 28.0000, Brandt excluded and non-transferable 1.5329; stage 6 shows Ostrander 142.0000, Kessler 124.2386, Banuelos 105.8190, Okafor 83.4095, Hargrove 81.0000, Szabo 28.0000, Wendling excluded and non-transferable 2.5329.",
  s7: "Stage 7 of the stage table shows Ostrander 142.0000, Kessler 124.2386, Banuelos 105.8190, Okafor 92.4095, Hargrove 98.0000, Szabo excluded and non-transferable 4.5329."
};
const DELETE = [/^The stage table in WBTC_2026_Director_Election_Certification\.docx gives these totals/,
                /^The stage table gives these totals from stage 1 until exclusion/,
                /^Candidates are excluded in this order/];
const EDIT = [[/^Stage 2 of the stage table/, 's2'],
              [/^Stages? 3 (and 4 )?of the stage table/, 's34'],
              [/^Stages? 5 (to 7 )?of the stage table/, 's56']];

const sleep = ms => new Promise(r => setTimeout(r, ms));
const log = (...a) => console.log('%c[fill]', 'color:#4f6228;font-weight:bold', ...a);
const warn = (...a) => console.warn('[fill] CHECK BY HAND:', ...a);
const txt = el => (el.innerText || el.textContent || '').trim();
const page = (document.body.innerText + ' ' + document.body.textContent).replace(/\s+/g, ' ');
if (!page.includes('bcf343ab')) { console.error('[fill] STOP: this is not task bcf343ab. Nothing was changed.'); return; }
const leafWith = re => [...document.querySelectorAll('body *')].filter(e => re.test(txt(e)) && ![...e.children].some(c => re.test(txt(c))));
function setVal(el, v) {
  const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  el.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
}
const headers = () => leafWith(/^Criterion \d+$/).filter(e => e.offsetParent !== null || e.getClientRects().length);
const maxCrit = () => Math.max(0, ...headers().map(h => +txt(h).split(' ')[1]));
function section(n) {
  const h = headers().find(e => txt(e) === 'Criterion ' + n); if (!h) return null;
  let el = h, best = h.parentElement;
  for (let i = 0; el && i < 10; i++, el = el.parentElement) {
    const names = new Set([...el.querySelectorAll('*')].filter(x => /^Criterion \d+$/.test(txt(x)) && !x.children.length).map(txt));
    if (names.size > 1) break;
    best = el;
  }
  return { h, box: best };
}
async function openSection(n) {
  const s = section(n); if (!s) return null;
  if (!s.box.querySelector('textarea')) { s.h.click(); await sleep(400); }
  const s2 = section(n);
  return s2 && s2.box.querySelector('textarea') ? s2 : null;
}

let start = maxCrit();
log('criteria on page before:', start);
let haveS7 = false;
const done = { s2: false, s34: false, s56: false }, deleted = [];
for (let n = start; n >= 1; n--) {
  const s = await openSection(n);
  if (!s) { warn('criterion', n, 'would not open'); continue; }
  const ta = s.box.querySelector('textarea'), v = ta.value.trim();
  if (v === NEW.s7) { haveS7 = true; log('criterion', n, 'is already the stage 7 one'); continue; }
  if (DELETE.some(re => re.test(v))) {
    const btn = [...s.box.querySelectorAll('button')].find(b => /delete section/i.test(txt(b)));
    if (btn) { btn.click(); await sleep(600); deleted.push(v.slice(0, 50)); log('criterion', n, 'deleted:', v.slice(0, 60)); }
    else warn('no Delete section button on criterion', n);
    continue;
  }
  for (const [re, key] of EDIT) {
    if (re.test(v)) {
      if (v === NEW[key]) log('criterion', n, 'already up to date');
      else { setVal(ta, NEW[key]); log('criterion', n, 'rewritten (' + key + '), weight kept'); }
      done[key] = true;
    }
  }
}
if (!haveS7) {
  const before = maxCrit();
  const add = [...document.querySelectorAll('button')].find(b => /add criterion/i.test(txt(b)));
  if (!add) warn('Add criterion button not found');
  else {
    add.click(); await sleep(800);
    const n = maxCrit();
    const s = n > before ? await openSection(n) : null;
    if (!s) warn('new criterion did not appear');
    else {
      setVal(s.box.querySelector('textarea'), NEW.s7);
      const w = [...s.box.querySelectorAll('input')].find(i => !['checkbox', 'radio', 'hidden', 'file'].includes(i.type));
      if (w) setVal(w, '2'); else warn('weight box for the new criterion not found, set it to 2');
      log('criterion', n, 'added: stage 7 (weight 2)');
    }
  }
}
for (const k of Object.keys(done)) if (!done[k]) warn('did not find the', k, 'criterion to rewrite');
if (deleted.length !== 3) warn('deleted', deleted.length, 'criteria, expected 3');
const end = maxCrit();
log('criteria on page now:', end, end === 23 ? '(correct)' : '(expected 23)');
log('done. Check the fields, then click Finish update yourself. Nothing was submitted.');
})();
