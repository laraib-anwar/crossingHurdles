(() => {
const UID = "70445e96";
const NEW = "batches.csv, blends.csv or shipments.csv is modified, renamed or deleted, whether by trace_recall.py when it runs or in the copies handed back with the submission.";
const txt = el => (el.innerText || el.textContent || '').trim();
if (!document.body.textContent.includes(UID)) { console.log('STOP: not task ' + UID + '. Nothing changed.'); return; }
const hits = [...document.querySelectorAll('textarea')].filter(t => /writes to, renames,? or deletes/i.test(t.value) && /batches\.csv/i.test(t.value));
if (!hits.length) { console.log('PROBLEM: the export-preservation criterion is not open or not found. Expand criterion 23 (the -5 one about writing to, renaming or deleting the csv files) and run this again.'); return; }
for (const t of hits) {
  console.log('OLD: ' + t.value);
  Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(t, NEW);
  t.dispatchEvent(new Event('input', { bubbles: true })); t.dispatchEvent(new Event('change', { bubbles: true })); t.blur();
  console.log('OK, NEW: ' + t.value + '  (weight left as it is)');
}
})();
