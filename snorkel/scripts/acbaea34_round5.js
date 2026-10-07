(async()=>{
const E=[["keying_now explains that Tuesday's make_key hashes", "keying_now explains that Tuesday's make_key ignores the Idempotency-Key header and hashes the raw request body bytes instead.", 5], ["Summary states 3 sandbox rows", "Summary states 3 sandbox rows held out of the production cut and reports 40 total traffic rows replayed, with those three sbx_demo requests making up the difference from the production count.", 4], ["keying_now explains that Tuesday's find_record", "keying_now explains that Tuesday's keying leaves tenant_id out of the store key and find_record matches store_key alone, so one tenant's record can be returned to another tenant.", 5]];const D=["The summary separately reports 40 total traffic rows"];const ADD=[["The deliverable is a single Excel workbook named exactly intake_idempo_book.xlsx, and its traffic_replay, same_intake and patched_eval sheets hold the replay rows, cluster analysis and patched code rather than placeholders.", 2]];const REVIEW="This round answers the rubric quality review. A criterion now names the exact deliverable file intake_idempo_book.xlsx and ties it to populated replay, cluster and patched-code sheets. The header-ignoring defect and the tenant-isolation defect are scored separately: criterion 1 covers make_key ignoring the Idempotency-Key header, and the find_record criterion now covers tenant_id being left out of the key and out of the lookup. The 40-row total was merged into the sandbox criterion so the production count is scored once. The rubric stays at 30 criteria. The prompt, inputs and golden are unchanged.";
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
const open=async i=>{let h=heads()[i];h.scrollIntoView({block:'center'});let c=box(h);if(!own(c)){h.click();await sleep(500);h=heads()[i];c=box(h);}return own(c)?c:null;};
const fill=(c,t,w)=>{const ta=c.querySelector('textarea');const wi=[...c.querySelectorAll('input')].find(x=>!['checkbox','radio','file','hidden','button','submit'].includes(x.type));setv(ta,t);if(wi)setv(wi,w);return ta.value===t&&wi&&String(wi.value)===String(w);};
const left=E.map(e=>e[0]);
for(let i=0;i<heads().length;i++){const c=await open(i);if(!c)continue;const v=c.querySelector('textarea').value;const hit=E.find(e=>v.startsWith(e[0]));if(!hit)continue;
  const ok=fill(c,hit[1],hit[2]);await sleep(250);console.log('Criterion',i+1,ok?'updated':'CHECK');left.splice(left.indexOf(hit[0]),1);}
if(left.length)console.error('Not found:',left);
for(const d of D){let done=false;for(let i=heads().length-1;i>=0&&!done;i--){const c=await open(i);if(!c)continue;if(c.querySelector('textarea').value.startsWith(d)){const b=delBtns(sec(heads()[i]))[0];b.scrollIntoView({block:'center'});b.click();await sleep(700);
  const ok=[...document.querySelectorAll('[role=dialog] button,[role=alertdialog] button')].find(x=>/^(delete|confirm|yes|ok)$/i.test(txt(x)));if(ok){ok.click();await sleep(700);}console.log('Deleted criterion',i+1);done=true;}}if(!done)console.error('Not found for delete:',d);}
const addBtn=()=>[...document.querySelectorAll('button')].find(b=>/add criterion/i.test(b.textContent));
for(const [t,w] of ADD){const n=heads().length;const b=addBtn();if(!b){console.error('Add criterion button not found');break;}b.scrollIntoView({block:'center'});b.click();await sleep(800);
  if(heads().length!==n+1){console.error('Add criterion did not create a slot');break;}const c=await open(n);const ok=c&&fill(c,t,w);await sleep(250);console.log('Added criterion',n+1,ok?'ok':'CHECK');}
console.log('Criteria on page:',heads().length,'(should be 30)');
const findLab=()=>all().find(e=>/^Briefly summarize the changes made/i.test(txt(e))&&e.children.length<3);
if(!findLab())await openSection(/^Section 3\s*[-–]\s*Review$/i);
const rl=findLab();const rta=rl&&[...document.querySelectorAll('textarea')].find(t=>rl.compareDocumentPosition(t)&4);
if(rta){setv(rta,REVIEW);console.log('Review',rta.value===REVIEW?'filled':'NOT SET');}else console.error('Review box not found');
console.log([...document.querySelectorAll('textarea')].some(t=>t!==rta&&t.value===REVIEW)?'WARNING: review text in another box':'Prompt is safe');
console.log('ALL DONE');
})();