(async()=>{
const EDIT={13:["The report correctly identifies that the July 20 scheduled publish_dashboard task was skipped or blocked after aggregate_daily_metrics failed, citing at least one of the supplied records that document it: run_history.csv, task_instances.csv, partition_state.csv, artifact_manifest.csv, or nextday_publish.log.",5]}; const ADD=["The deliverable is a Word document named sales_incident_report.docx that contains the incident report rather than an empty or placeholder file.",1];
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const txt=e=>(e.textContent||'').replace(/\s+/g,' ').trim();
const isHead=e=>/^Criterion ?\d+$/.test(txt(e));
const delBtns=c=>[...c.querySelectorAll('button')].filter(b=>/delete section/i.test(b.textContent));
const inForm=e=>{let c=e;for(let k=0;k<5&&c;k++){c=c.parentElement;if(c&&delBtns(c).length===1)return true;}return false;};
const heads=()=>[...document.querySelectorAll('body *')].filter(e=>isHead(e)&&![...e.children].some(isHead)&&inForm(e));
const addBtn=()=>[...document.querySelectorAll('button')].find(b=>/add criterion/i.test(b.textContent));
const set=(el,v)=>{const p=el instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;el.focus();Object.getOwnPropertyDescriptor(p,'value').set.call(el,String(v));el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));el.blur();};
const box=h=>{let c=h.parentElement;while(c&&!c.querySelector('textarea'))c=c.parentElement;return c;};
const own=c=>c&&heads().filter(x=>c.contains(x)).length===1&&delBtns(c).length<=1;
const fill=async(i,t,w)=>{let h=heads()[i];h.scrollIntoView({block:'center'});let c=box(h);if(!own(c)){h.click();await sleep(600);h=heads()[i];c=box(h);}
  if(!own(c)){console.error('Could not open criterion',i+1);return;}
  const ta=c.querySelector('textarea');const wi=[...c.querySelectorAll('input')].find(x=>!['checkbox','radio','file','hidden','button','submit'].includes(x.type));
  set(ta,t);if(wi)set(wi,w);await sleep(300);console.log('Criterion',i+1,ta.value===t?'text ok':'TEXT NOT SET',wi&&String(wi.value)===String(w)?'weight ok':'CHECK WEIGHT');};
const n=heads().length;console.log('Criteria on page before:',n);
if(n!==28){console.error('Expected 28 criteria on the page, found '+n+'. Stopping so nothing gets overwritten.');return;}
await fill(12,EDIT[13][0],EDIT[13][1]);
addBtn().scrollIntoView({block:'center'});addBtn().click();await sleep(800);
if(heads().length!==29){console.error('Add criterion did not create slot 29');return;}
await fill(28,ADD[0],ADD[1]);
console.log('DONE. Criteria on page: '+heads().length);
})();