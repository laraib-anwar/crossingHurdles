(async()=>{
const REVIEW="This round fixes the four Major findings and three of the four Minor ones without adding criteria. Inputs: recovery_exercise_constraints.xlsx gains CTL-015, which makes a passing Component failover test support only a provisional Full failover call that falls to Observe Only without production-equivalent confirmation by the decision gate; restore_test_results.xlsx now leaves SVC-08's recovery and loss minutes blank because the test was not run. Rubric: the cohort, wave-order and SVC-06 criteria now accept either the provisional Full failover reading or Observe Only pending evidence; the blocker criterion binds RA-401 to RA-404 to their services and required work; the evidence-capture checklist criterion requires all five per-service times with rollback not applicable where none occurs; the rollback criterion requires the Incident Commander and all three CTL-041 stop conditions; the matrix test criterion accepts not measured for SVC-08; the row-label criterion was merged into the service_inventory row check, the decision criterion now requires decisions consistent with the evidence and CTL rules, and the file criterion was reduced to weight 1. Golden: the matrix marks SVC-06 Full (provisional) and SVC-08 not measured, the SVC-06 note cites CTL-015, and the checklist records the five times per service. The concise-narrative Minor was not given a separate criterion to keep the rubric from growing. The prompt is unchanged.";
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const txt=e=>(e.textContent||'').replace(/\s+/g,' ').trim();
const setv=(el,v)=>{const p=HTMLTextAreaElement.prototype;el.focus();Object.getOwnPropertyDescriptor(p,'value').set.call(el,String(v));el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));el.blur();};
const findLab=()=>[...document.querySelectorAll('body *')].find(e=>/^Briefly summarize the changes made/i.test(txt(e))&&e.children.length<3);
let lab=findLab();
if(!lab){const h=[...document.querySelectorAll('body *')].find(e=>/^Section 3\s*[-–]\s*Review$/i.test(txt(e)));if(h){h.scrollIntoView({block:'center'});h.click();await sleep(900);}lab=findLab();}
if(!lab){console.error('Review question not visible. Click "Section 3 - Review" to open it, then run this again.');return;}
const ta=[...document.querySelectorAll('textarea')].find(t=>lab.compareDocumentPosition(t)&Node.DOCUMENT_POSITION_FOLLOWING);
if(!ta){console.error('Review box not found after the question');return;}
const others=[...document.querySelectorAll('textarea')].filter(t=>t!==ta&&t.value===REVIEW);
ta.scrollIntoView({block:'center'});setv(ta,REVIEW);
console.log('Review',ta.value===REVIEW?'filled':'NOT SET');
if(others.length)console.error('WARNING: '+others.length+' other box(es) also contain the review text (likely the User Prompt). Reload the page to restore the prompt, then run only the review script again.');
else console.log('No other box contains the review text. Prompt is safe.');
})();