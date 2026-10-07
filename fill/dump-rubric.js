(async () => {
// READ ONLY: copies the prompt and every criterion (number | weight | text) to the clipboard. Changes nothing.
const sleep = ms => new Promise(r => setTimeout(r, ms));
const txt = el => (el.innerText || el.textContent || '').trim();
const uid = (document.body.textContent.match(/UID:\s*([0-9a-f]{8})/i) || [])[1] || '?';
const leaves = re => [...document.querySelectorAll('body *')].filter(e => re.test(txt(e)) && ![...e.children].some(c => re.test(txt(c))));
const nums = () => leaves(/^Criterion \d+$/).map(h => +txt(h).split(' ')[1]);
const box = n => { const h = leaves(/^Criterion \d+$/).find(e => txt(e) === 'Criterion ' + n); if (!h) return null; let el = h, best = h.parentElement; for (let i = 0; el && i < 10; i++, el = el.parentElement) { const s = new Set([...el.querySelectorAll('*')].filter(x => /^Criterion \d+$/.test(txt(x)) && !x.children.length).map(txt)); if (s.size > 1) break; best = el; } return { h, best }; };
const prompt = [...document.querySelectorAll('textarea')].sort((x, y) => y.value.length - x.value.length)[0];
let out = 'TASK ' + uid + '\nPROMPT:\n' + (prompt ? prompt.value : '(not found)') + '\n\nCRITERIA:\n';
for (const n of nums()) {
  let b = box(n);
  if (b && !b.best.querySelector('textarea')) { b.h.click(); await sleep(400); b = box(n); }
  const t = b && b.best.querySelector('textarea');
  const w = b && [...b.best.querySelectorAll('input')].find(i => !['checkbox', 'radio', 'hidden', 'file'].includes(i.type));
  out += n + ' | ' + (w ? w.value : '?') + ' | ' + (t ? t.value.replace(/\s+/g, ' ').trim() : '(would not open)') + '\n';
}
try { copy(out); console.log('%cCopied to clipboard: prompt + ' + nums().length + ' criteria. Paste it into the chat.', 'color:#2f6b2f;font-weight:bold'); }
catch (e) { console.log('Could not copy automatically. Right-click the text below, choose "Copy string contents", and paste it into the chat.'); }
console.log(out);
})();
