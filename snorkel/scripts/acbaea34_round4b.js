(async()=>{
const E=[["The deliverable ", "The deliverable states or indicates that the live intake host intake.manitowocclaims.internal or material outside the supplied folder was accessed, or cites records or figures that cannot be traced to the supplied files.", -3]];const REVIEW="This round fixes the one remaining Minor on the live-host rule. The penalty now fires on what a grader can see in the workbook: any statement or indication that intake.manitowocclaims.internal or material outside the supplied folder was accessed, or any cited record or figure that cannot be traced to the supplied files. No criterion was added; the rubric stays at 30. The prompt, inputs and golden are unchanged and the golden does none of these things.";
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
let found=false;
for(let i=0;i<heads().length&&!found;i++){let h=heads()[i];let c=box(h);if(!own(c)){h.click();await sleep(500);h=heads()[i];c=box(h);}if(!own(c))continue;
  const ta=c.querySelector('textarea');const hit=E.find(e=>ta.value.startsWith(e[0]));if(!hit)continue;
  const w=[...c.querySelectorAll('input')].find(x=>!['checkbox','radio','file','hidden','button','submit'].includes(x.type));
  ta.scrollIntoView({block:'center'});setv(ta,hit[1]);if(w)setv(w,hit[2]);await sleep(250);console.log('Criterion',i+1,ta.value===hit[1]?'updated':'NOT SET',w&&String(w.value)===String(hit[2])?'weight ok':'CHECK WEIGHT');found=true;}
if(!found)console.error('Live-host criterion not found');
console.log('Criteria on page:',heads().length,'(should be 30)');
const findLab=()=>all().find(e=>/^Briefly summarize the changes made/i.test(txt(e))&&e.children.length<3);
if(!findLab())await openSection(/^Section 3\s*[-–]\s*Review$/i);
const rl=findLab();const rta=rl&&[...document.querySelectorAll('textarea')].find(t=>rl.compareDocumentPosition(t)&4);
if(rta){setv(rta,REVIEW);console.log('Review',rta.value===REVIEW?'filled':'NOT SET');}else console.error('Review box not found');
console.log([...document.querySelectorAll('textarea')].some(t=>t!==rta&&t.value===REVIEW)?'WARNING: review text in another box':'Prompt is safe');
console.log('ALL DONE');
})();