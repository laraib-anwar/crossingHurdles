(async()=>{
const E=[["The report separates verified operational impact", "sales_incident_report.docx separates verified operational impact from impact the supplied records do not establish, naming customer impact, monetary impact, affected business users, and quantified internal-audit impact as not established.", 5]];const D=["The deliverable is a Word document named sales_incident_report.docx"];const REVIEW="This round fixes the golden-check variance and the two Minor findings. Golden: the not-established impact list now names customer impact, monetary impact, affected business users and quantified internal-audit impact in those words, so the impact criterion can be verified on every run; no finding changed. Rubric: the weight-1 filename criterion was removed as a scored item and the exact file name now sits in the substantive impact criterion, so the name is still graded but only with real content. The rubric has 23 criteria. Inputs: retry_pipeline.log records the raw extract at 02:18:00Z and the staging recompute at 02:19:58Z as separate lines, matching task_instances.csv and cache_registry.csv. The prompt is unchanged.";
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
const open=async i=>{let h=heads()[i];let c=box(h);if(!own(c)){h.click();await sleep(500);h=heads()[i];c=box(h);}return own(c)?c:null;};
for(let i=0;i<heads().length;i++){const c=await open(i);if(!c)continue;const ta=c.querySelector('textarea');const hit=E.find(e=>ta.value.startsWith(e[0]));if(!hit)continue;
  const w=[...c.querySelectorAll('input')].find(x=>!['checkbox','radio','file','hidden','button','submit'].includes(x.type));
  ta.scrollIntoView({block:'center'});setv(ta,hit[1]);if(w)setv(w,hit[2]);await sleep(250);console.log('Criterion',i+1,ta.value===hit[1]?'updated':'NOT SET');}
for(const d of D){let done=false;for(let i=heads().length-1;i>=0&&!done;i--){const c=await open(i);if(!c)continue;if(c.querySelector('textarea').value.startsWith(d)){const b=delBtns(sec(heads()[i]))[0];b.scrollIntoView({block:'center'});b.click();await sleep(700);
  const ok=[...document.querySelectorAll('[role=dialog] button,[role=alertdialog] button')].find(x=>/^(delete|confirm|yes|ok)$/i.test(txt(x)));if(ok){ok.click();await sleep(700);}console.log('Deleted criterion',i+1);done=true;}}if(!done)console.error('Not found for delete:',d);}
console.log('Criteria on page:',heads().length,'(should be 23)');
const findLab=()=>all().find(e=>/^Briefly summarize the changes made/i.test(txt(e))&&e.children.length<3);
if(!findLab())await openSection(/^Section 3\s*[-–]\s*Review$/i);
const rl=findLab();const rta=rl&&[...document.querySelectorAll('textarea')].find(t=>rl.compareDocumentPosition(t)&4);
if(rta){setv(rta,REVIEW);console.log('Review',rta.value===REVIEW?'filled':'NOT SET');}else console.error('Review box not found');
console.log([...document.querySelectorAll('textarea')].some(t=>t!==rta&&t.value===REVIEW)?'WARNING: review text in another box':'Prompt is safe');
console.log('ALL DONE');
})();