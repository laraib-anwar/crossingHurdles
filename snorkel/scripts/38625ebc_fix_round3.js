(async()=>{
const TARGETS=["The report definitively attributes the July 21 reused fact artifact","The report definitively asserts that run_2026_07_20_scheduled and run_2026_07_20_backfill overlapped"];
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const txt=e=>(e.textContent||'').replace(/\s+/g,' ').trim();
const isHead=e=>/^Criterion ?\d+$/.test(txt(e));
const delBtns=c=>[...c.querySelectorAll('button')].filter(b=>/delete section/i.test(b.textContent));
const inForm=e=>{let c=e;for(let k=0;k<5&&c;k++){c=c.parentElement;if(c&&delBtns(c).length===1)return true;}return false;};
const heads=()=>[...document.querySelectorAll('body *')].filter(e=>isHead(e)&&![...e.children].some(isHead)&&inForm(e));
const box=h=>{let c=h.parentElement;while(c&&!c.querySelector('textarea'))c=c.parentElement;return c;};
const own=c=>c&&heads().filter(x=>c.contains(x)).length===1&&delBtns(c).length<=1;
const section=h=>{let c=h;for(let k=0;k<5&&c;k++){c=c.parentElement;if(c&&delBtns(c).length===1)return c;}return null;};
const valueAt=async i=>{let h=heads()[i];h.scrollIntoView({block:'center'});let c=box(h);if(!own(c)){h.click();await sleep(500);h=heads()[i];c=box(h);}return own(c)?c.querySelector('textarea').value:null;};
console.log('Criteria on page before:',heads().length);
for(const t of TARGETS){
  let found=-1;
  for(let i=heads().length-1;i>=0;i--){const v=await valueAt(i);if(v&&v.startsWith(t)){found=i;break;}}
  if(found<0){console.error('Not found (maybe already deleted):',t.slice(0,60));continue;}
  const sec=section(heads()[found]);const b=delBtns(sec)[0];b.scrollIntoView({block:'center'});b.click();await sleep(700);
  const ok=[...document.querySelectorAll('[role=dialog] button,[role=alertdialog] button')].find(x=>/^(delete|confirm|yes|ok)$/i.test(txt(x)));
  if(ok){ok.click();await sleep(700);}
  console.log('Deleted criterion',found+1,':',t.slice(0,60));
}
console.log('DONE. Criteria on page: '+heads().length);
})();
