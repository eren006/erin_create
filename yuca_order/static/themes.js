(function(){
  const names={ink:'眠眠岁岁',ballet:'红眼尾'};
  const headingCopies=[];
  function applyTheme(id,persist){
    id=Object.prototype.hasOwnProperty.call(names,id)?id:'ink';
    document.documentElement.setAttribute('data-theme',id);
    if(persist){try{localStorage.setItem('yuca-theme-v2',id);}catch(e){}}
    document.querySelectorAll('[data-theme-picker]').forEach(el=>el.value=id);
    document.querySelectorAll('[data-theme-name]').forEach(el=>el.textContent=names[id]);
    document.querySelectorAll('[data-ink-copy][data-ballet-copy]').forEach(el=>{
      el.textContent=id==='ballet'?el.dataset.balletCopy:el.dataset.inkCopy;
    });
    headingCopies.forEach(item=>{if(id==='ink')item.element.innerHTML=item.inkHTML;else item.element.textContent=item.balletText;});
    document.dispatchEvent(new CustomEvent('themechange',{detail:{theme:id}}));
  }
  document.querySelectorAll('[data-theme-picker]').forEach(el=>{
    el.addEventListener('change',()=>applyTheme(el.value,true));
  });
  // Preserve existing wording for ink and provide matching ballet copy.
  const headings=document.querySelectorAll('.inner-masthead h1');
  headings.forEach(el=>{
    const ep=document.body.dataset.page||'';
    const balletText=document.body.classList.contains('auth-page')?'轻盈相逢，灵感起舞':
      (ep.startsWith('admin_')||ep.startsWith('superadmin_'))?'幕后有序，台前从容':
      ep==='order_new'?'让每一份灵感，轻盈登场。':'每一份创作，都有回音。';
    headingCopies.push({element:el,inkHTML:el.innerHTML,balletText});
  });
  applyTheme(document.documentElement.getAttribute('data-theme'),false);
  window.addEventListener('storage',e=>{if(e.key==='yuca-theme-v2')applyTheme(e.newValue,false);});
})();
