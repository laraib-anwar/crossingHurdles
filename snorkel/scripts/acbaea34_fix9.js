(async()=>{
const NEW9="In intake_idempo_book.xlsx, the summary cells for production traffic rows, same-intake duplicate clusters, cross-tenant store hits, TTL-misapplied rows and sandbox rows are Excel formulas over traffic_replay or same_intake rather than typed numbers.";
const OLD_REV="the exact file name now sits in the summary-formula criterion, which requires the formulas to evaluate to 37, 3, 1, 1 and 3.";
const NEW_REV="the exact file name now sits in the summary-formula criterion, which checks only that those summary cells are formulas; the values themselves stay graded by their own criteria.";
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const txt=e=>(e.textContent||'').replace(/\s+/g,' ').trim();
const setv=(el,v)=>{const p=HTMLTextAreaElement.prototype;el.focus();Object.getOwnPropertyDescriptor(p,'value').set.call(el,String(v));el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));el.blur();};
const all=()=>[...document.querySelectorAll('body *')];
const openSection=async re=>{const h=all().find(e=>re.test(txt(e))&&e.children.length<4);if(h){h.scrollIntoView({block:'center'});h.click();await sleep(900);}};
const isHead=e=>/^Criterion ?\d+$/.test(txt(e));
const delBtns=c=>[...c.querySelectorAll('button')].filter(b=>/delete section/i.test(b.textContent));
const sec=e=>{let c=e;for(let k=0;k<5&&c;k++){c=c.parentElement;if(c&&delBtns(c).length===1)return c;}return null;};
const heads=()=>all().filter(e=>isHead(e)&&![...e.children].some(isHead)&&sec(e));
if(!heads().length)await openSection(/^Section 2\s*[-–]\s*Golden Solution and Rubric$/i);
const box=h=>{let c=h.parentElement;while(c&&!c.querySelector('textarea'))c=c.parentElement;return c;};
const own=c=>c&&heads().filter(x=>c.contains(x)).length===1&&delBtns(c).length<=1;
let done=false;
for(let i=0;i<heads().length&&!done;i++){
  let h=heads()[i];let c=box(h);if(!own(c)){h.click();await sleep(500);h=heads()[i];c=box(h);}
  if(!own(c))continue;const ta=c.querySelector('textarea');
  if(ta.value.startsWith('In intake_idempo_book.xlsx, the summary')){ta.scrollIntoView({block:'center'});setv(ta,NEW9);console.log('Criterion',i+1,ta.value===NEW9?'updated':'NOT SET');done=true;}
}
if(!done)console.error('Formula criterion not found');
const findLab=()=>all().find(e=>/^Briefly summarize the changes made/i.test(txt(e))&&e.children.length<3);
if(!findLab())await openSection(/^Section 3\s*[-–]\s*Review$/i);
const rl=findLab();const rta=rl&&[...document.querySelectorAll('textarea')].find(t=>rl.compareDocumentPosition(t)&4);
if(rta&&rta.value.includes(OLD_REV)){setv(rta,rta.value.replace(OLD_REV,NEW_REV));console.log('Review updated');}else console.log('Review left as is (sentence not found)');
console.log('ALL DONE');
})();
