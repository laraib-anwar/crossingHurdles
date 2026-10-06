(async()=>{
const E=[["The submission contains one Word document", "November_Recovery_Exercise_Brief.docx opens without a repair prompt and contains an executive recommendation, a wave-by-wave plan, a service readiness matrix, a blocker section, and an operator checklist.", 1], ["The brief puts SVC-01, SVC-03, SVC-11 and SVC-12", "The brief puts SVC-01, SVC-03, SVC-11 and SVC-12 in Full Failover, cuts SVC-05 over only when SVC-06 cuts over, and states the same decisions in the executive recommendation and the matrix.", 5], ["The operator checklist requires an explicit go or no go", "The operator checklist requires the final go/no-go roster to be confirmed against the 2026-10-30 evidence gate and approved scope changes to be recorded.", 2], ["The operator checklist requires data and queued work to be reconciled", "The operator checklist includes reconciling data and queued work during the exercise.", 1]];
const REVIEW="This round fixes the quality judge's one Major and three Minor findings in the rubric only; the prompt, inputs and golden are unchanged and the golden satisfies every revised criterion. Major: the go/no-go criterion no longer mandates a pre-release scope decision; it now credits confirming the final go/no-go roster against the 2026-10-30 evidence gate and recording approved scope changes, which CTL-002 supports. Minors: the reconciliation criterion now checks only that data and queued work are reconciled, without an unstated between-wave gate; the cohort criterion no longer grades SVC-06, which stays with the SVC-06 evidence-type criterion, so the same call is not counted twice; and the file criterion now requires the named DOCX to contain the recommendation, wave plan, readiness matrix, blocker section and operator checklist. The rubric stays at 32 criteria.";
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const txt=e=>(e.textContent||'').replace(/\s+/g,' ').trim();
const setv=(el,v)=>{const p=el instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;el.focus();Object.getOwnPropertyDescriptor(p,'value').set.call(el,String(v));el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));el.blur();};
const all=()=>[...document.querySelectorAll('body *')];
const openSection=async re=>{const h=all().find(e=>re.test(txt(e))&&e.children.length<4);if(h){h.scrollIntoView({block:'center'});h.click();await sleep(900);}};
const isHead=e=>/^Criterion ?\d+$/.test(txt(e));
const delBtns=c=>[...c.querySelectorAll('button')].filter(b=>/delete section/i.test(b.textContent));
const sec=e=>{let c=e;for(let k=0;k<5&&c;k++){c=c.parentElement;if(c&&delBtns(c).length===1)return c;}return null;};
const heads=()=>all().filter(e=>isHead(e)&&![...e.children].some(isHead)&&sec(e));
if(!heads().length)await openSection(/^Section 2\s*[-–]\s*Golden Solution and Rubric$/i);
const box=h=>{let c=h.parentElement;while(c&&!c.querySelector('textarea'))c=c.parentElement;return c;};
const own=c=>c&&heads().filter(x=>c.contains(x)).length===1&&delBtns(c).length<=1;
const left=E.map(e=>e[0]);
for(let i=0;i<heads().length;i++){
  let h=heads()[i];let c=box(h);if(!own(c)){h.click();await sleep(500);h=heads()[i];c=box(h);}
  if(!own(c))continue;const ta=c.querySelector('textarea');
  const hit=E.find(e=>ta.value.startsWith(e[0]));if(!hit)continue;
  const w=[...c.querySelectorAll('input')].find(x=>!['checkbox','radio','file','hidden','button','submit'].includes(x.type));
  ta.scrollIntoView({block:'center'});setv(ta,hit[1]);if(w)setv(w,hit[2]);await sleep(250);
  console.log('Criterion',i+1,ta.value===hit[1]?'updated':'NOT SET',w&&String(w.value)===String(hit[2])?'weight ok':'CHECK WEIGHT');
  left.splice(left.indexOf(hit[0]),1);
}
if(left.length)console.error('Not found:',left);
console.log('Criteria on page:',heads().length,'(should be 32)');
const findLab=()=>all().find(e=>/^Briefly summarize the changes made/i.test(txt(e))&&e.children.length<3);
if(!findLab())await openSection(/^Section 3\s*[-–]\s*Review$/i);
const rl=findLab();const rta=rl&&[...document.querySelectorAll('textarea')].find(t=>rl.compareDocumentPosition(t)&4);
if(rta){setv(rta,REVIEW);console.log('Review',rta.value===REVIEW?'filled':'NOT SET');}else console.error('Review box not found');
console.log([...document.querySelectorAll('textarea')].some(t=>t!==rta&&t.value===REVIEW)?'WARNING: review text in another box':'Prompt is safe');
console.log('ALL DONE');
})();