(function () {
  'use strict';
  const root = document.querySelector('[data-explore]');
  if (!root) return;
  const mode = root.dataset.explore, admin = mode === 'admin', csrf = root.dataset.csrf || '';
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const date = (ts) => new Intl.DateTimeFormat('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Shanghai'}).format(new Date(ts));
  function message(el, text, error = false) { el.textContent = text || ''; el.hidden = !text; el.classList.toggle('is-error', error); }
  function fail(el, err) {
    message(el, err.message || '暂时没有连上，请稍后再试。', true);
    if (err.status === 403) { const b=document.createElement('button'); b.type='button';b.className='xp-button xp-quiet';b.textContent='重新打开页面';b.onclick=()=>location.reload();el.append(document.createElement('br'),b); }
  }
  function feedback(form) { return form.querySelector('[data-feedback]'); }
  async function request(path, body) {
    const controller = new AbortController(), timeout = setTimeout(()=>controller.abort(),40000);
    const opts = {credentials:'same-origin', signal:controller.signal, headers:{'Accept':'application/json'}};
    if (body !== undefined) {
      opts.method='POST'; opts.headers['X-CSRF']=csrf;
      if (body instanceof FormData) opts.body=body;
      else { opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(body); }
    }
    try {
      const res=await fetch(path,opts);
      if (res.redirected || res.status===401) {
        if (admin) { const err=new Error('登录已过期，请重新登录后台。');err.status=403;throw err; }
        location.assign('/x');throw new Error('登录已过期，正在返回入口。');
      }
      const data=await res.json();
      if (!res.ok || !data.ok) { const err=new Error(data.error || '这次操作没有完成，请稍后再试。');err.status=res.status;err.data=data;throw err; }
      return data;
    } catch (err) {
      if (!err.status) err.message=body!==undefined ? '连接中断，结果暂未确认。先更新记录核对，再决定是否重试。' : '暂时没有连上，请重试。';
      throw err;
    } finally { clearTimeout(timeout); }
  }
  async function lock(container, task) {
    if (container.dataset.busy) return;
    container.dataset.busy='1';container.setAttribute('aria-busy','true');
    const controls=[...container.querySelectorAll('button,input,select,textarea')], disabled=controls.map(c=>c.disabled);
    controls.forEach(c=>c.disabled=true);
    try { return await task(); }
    finally { controls.forEach((c,i)=>c.disabled=disabled[i]);delete container.dataset.busy;container.removeAttribute('aria-busy'); }
  }
  function status(value) {
    return value ? `<span class="xp-status ${esc(value)}">${{pending:'入包中',ok:'已入包',failed:'入包失败 · 请联系管理员'}[value] || '待确认'}</span>` : '';
  }
  function logHTML(rows, showRole=false) {
    if (!rows.length) return '<p class="xp-empty">还没有足迹。<br>去探索看看吧。</p>';
    return rows.map(r=>`<article class="xp-log-row"><time datetime="${esc(new Date(r.ts).toISOString())}">${esc(date(r.ts))} · 北京时间</time><p>${showRole ? esc(r.role)+' · ' : ''}${esc(r.spot)}</p><h3>${esc(r.title)}</h3>${r.text?`<p>${esc(r.text)}</p>`:''}${status(r.item_status)}${r.used==='bonus'?'<span class="xp-status">临时次数</span>':''}</article>`).join('');
  }
  // The entry/logout endpoints intentionally return HTML redirects, unlike the JSON APIs.
  async function submitEntry(form) {
    const body=new FormData(form), button=form.querySelector('button'), original=button.textContent;
    await lock(form,async()=>{
      button.textContent='正在打开…';
      try {
        const res=await fetch(form.action,{method:'POST',body,credentials:'same-origin'});
        if(res.redirected){location.assign(res.url);return;}
        const doc=new DOMParser().parseFromString(await res.text(),'text/html');
        message($('xp-entry-message'),doc.querySelector('#xp-entry-message')?.textContent.trim() || '激活码没有匹配上，请再核对一下。',true);
      } catch (_) {message($('xp-entry-message'),'暂时没有连上，请稍后再试。',true);}
      finally {button.textContent=original;}
    });
  }
  if (mode==='entry') {
    const form=$('xp-entry'), input=$('xp-code');
    input.addEventListener('input',()=>{const start=input.selectionStart,end=input.selectionEnd;input.value=input.value.toUpperCase();input.setSelectionRange(start,end);});
    form.addEventListener('submit',e=>{e.preventDefault();submitEntry(form);});return;
  }
  if (!admin) {
    let state=null, mapId=null, active='map', clues=[], clueRequest=0, logRequest=0, logTimer=null, visiting=false, currentSpot=null, exhausted=false, clueView='spot';
    const sheet=$('xp-spot-sheet');
    function quota(q) {
      if(q) {state.quota=q;$('xp-quota').innerHTML=`<span>今日的脚步</span><strong>${esc(q.total)}<small>次</small></strong><span>日常 ${esc(q.daily_left)} / ${esc(q.daily_limit)} · 临时 ${esc(q.bonus)}</span>`;}
      if(currentSpot) updateVisitButton();
    }
    function badge(n) {const el=$('xp-clue-badge');el.textContent=n>99?'99+':String(n||0);el.hidden=!n;}
    function updateVisitButton() {
      const q=state?.quota || {total:0,daily_left:0,bonus:0}, button=$('xp-visit');
      $('xp-sheet-quota').innerHTML=`今日剩余 <strong>${esc(q.daily_left)}</strong> 次 · 临时 <strong>${esc(q.bonus)}</strong> 次`;
      button.disabled=visiting || exhausted || !state?.enabled || q.total<=0;
      button.textContent=visiting?'正在探索…':exhausted?'这里没有新发现了':q.total<=0?'今天的次数用完了':'踩点';
    }
    function openSpot(spot, map) {
      if(visiting){message($('xp-global-message'),'上一处还在探索中，等结果回来再出发。');return;}
      currentSpot=spot;exhausted=false;
      $('xp-sheet-map').textContent=map.name;$('xp-sheet-title').textContent=spot.name;$('xp-sheet-desc').textContent=spot.desc||'慢一点，看看有没有被忽略的细节。';$('xp-sheet-icon').textContent=spot.icon||'📍';
      $('xp-visit-result').hidden=true;message($('xp-sheet-message'),'');updateVisitButton();sheet.showModal();
    }
    function renderMap() {
      const box=$('xp-map-content');
      if (!state?.enabled) {box.innerHTML='<p class="xp-empty">探索还没有开放</p>';$('xp-map-tabs').replaceChildren();return;}
      const maps=state.maps||[], map=maps.find(m=>m.id===mapId)||maps[0];
      if(!map){box.innerHTML='<p class="xp-empty">地图还在绘制。<br>等一个可以出发的地方。</p>';$('xp-map-tabs').replaceChildren();return;}
      mapId=map.id;
      $('xp-map-tabs').innerHTML=maps.length>1?maps.map(m=>`<button type="button" data-map-id="${m.id}" aria-pressed="${m.id===mapId}">${esc(m.name)}</button>`).join(''):'';
      let html='';
      if(map.image) html=`<div class="xp-map-frame"><div class="xp-map-stage"><img src="${esc(map.image)}" alt="${esc(map.name)}地图">${map.spots.map(s=>`<button class="xp-pin" data-spot="${s.id}" style="--pin-x:${Number(s.x)}%;--pin-y:${Number(s.y)}%" aria-label="探索${esc(s.name)}"><span aria-hidden="true">${esc(s.icon||'📍')}</span><small aria-hidden="true">${esc(s.name)}</small></button>`).join('')}</div><div class="xp-map-caption"><span>${esc(map.name)}</span><span>点标记，或从下方选择</span></div></div>`;
      html+=map.spots.length?`<div class="xp-place-list">${map.spots.map(s=>`<button class="xp-place-card" data-spot="${s.id}"><span class="xp-place-icon" aria-hidden="true">${esc(s.icon||'📍')}</span><div><strong>${esc(s.name)}</strong><p>${esc(s.desc||'看看这里藏着什么。')}</p></div><span aria-hidden="true">↗</span></button>`).join('')}</div>`:'<p class="xp-empty">这张地图上的地点还没开放。</p>';
      box.innerHTML=html;
      box.querySelectorAll('[data-spot]').forEach(b=>b.onclick=()=>openSpot(map.spots.find(s=>s.id===Number(b.dataset.spot)),map));
      box.querySelector('img')?.addEventListener('error',()=>{box.querySelector('.xp-map-frame').hidden=true;message($('xp-global-message'),'地图图片暂时没有加载出来，可以从地点列表继续探索。');});
    }
    $('xp-map-tabs').addEventListener('click',e=>{const b=e.target.closest('[data-map-id]');if(b){mapId=Number(b.dataset.mapId);renderMap();}});
    async function loadState() {
      const b=$('xp-reload-state');b.disabled=true;
      try {state=await request('/x/api/state');quota(state.quota);badge(state.clue_new||0);$('xp-intro').textContent=state.enabled?(state.intro||'挑一个地方，把今天的第一步留在那里。'):'';$('xp-quota').hidden=!state.enabled;$('xp-panel-map').querySelector('.xp-section-head').hidden=!state.enabled;renderMap();message($('xp-global-message'),'');}
      catch(err){fail($('xp-global-message'),err);$('xp-map-content').innerHTML='<p class="xp-empty">地图暂时没有展开，点右上角重试。</p>';}
      finally{b.disabled=false;}
    }
    function clueCard(c,i,byTime) {
      return `<article class="xp-clue">${c.new?'<span class="xp-new">新</span>':''}<span class="xp-eyebrow">线索 · ${String(i+1).padStart(2,'0')}</span><h3>${esc(c.title)}</h3><p>${esc(c.text)}</p><footer>${byTime?esc(c.map?c.map+' · ':'')+esc(c.spot)+'<br>':''}${esc(date(c.ts))} · 北京时间</footer></article>`;
    }
    function renderClues() {
      const query=$('xp-clue-search').value.trim().toLocaleLowerCase(), rows=clues.filter(c=>[c.title,c.text,c.spot,c.map].join(' ').toLocaleLowerCase().includes(query));
      $('xp-clue-count').textContent=`${clues.length} 条线索`;
      document.querySelectorAll('#xp-clue-view button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===clueView)));
      const empty=`<p class="xp-empty">${clues.length?'没有找到这条线索，换个词试试。':'手账里还没有线索。<br>去探索看看吧。'}</p>`;
      if(!rows.length){$('xp-clue-list').innerHTML=empty;return;}
      if(clueView==='time'){$('xp-clue-list').innerHTML=rows.map((c,i)=>clueCard(c,i,true)).join('');return;}
      const groups=new Map();
      rows.forEach(c=>{const k=(c.map||'')+'\u0000'+c.spot;if(!groups.has(k))groups.set(k,{map:c.map,spot:c.spot,items:[]});groups.get(k).items.push(c);});
      const list=[...groups.values()];
      list.forEach(g=>{g.items.sort((x,y)=>x.ts-y.ts);g.last=g.items[g.items.length-1].ts;});
      list.sort((x,y)=>y.last-x.last);
      $('xp-clue-list').innerHTML=list.map(g=>`<section class="xp-clue-group"><h3 class="xp-clue-group-head"><span>${esc(g.map?g.map+' · ':'')}${esc(g.spot)}</span><small>${g.items.length} 条${g.items.some(c=>c.new)?' · 有新线索':''}</small></h3><div class="xp-clue-wall">${g.items.map((c,i)=>clueCard(c,i,false)).join('')}</div></section>`).join('');
    }
    async function loadClues() {
      const revision=++clueRequest;$('xp-clue-list').innerHTML='<p class="xp-empty">正在整理线索…</p>';
      try {const data=await request('/x/api/clues');if(revision!==clueRequest)return;clues=data.clues;renderClues();if(active==='clues'&&clues.some(c=>c.new)){await request('/x/api/clues/seen',{});badge(0);if(state)state.clue_new=0;}}
      catch(err){fail($('xp-global-message'),err);if(!clues.length)$('xp-clue-list').innerHTML='<p class="xp-empty">线索暂时没有加载成功，重新点标签可重试。</p>';}
    }
    async function loadLog() {
      clearTimeout(logTimer);const revision=++logRequest,b=$('xp-reload-log');b.disabled=true;
      try{const data=await request('/x/api/log');if(revision===logRequest){$('xp-log-list').innerHTML=logHTML(data.log);if(active==='log'&&data.log.some(r=>r.item_status==='pending'))logTimer=setTimeout(()=>{if(active==='log'&&!document.hidden)loadLog();},8000);}}
      catch(err){fail($('xp-global-message'),err);}
      finally{if(revision===logRequest)b.disabled=false;}
    }
    async function tab(name) {
      active=name;clearTimeout(logTimer);
      document.querySelectorAll('[data-tab]').forEach(b=>{b.setAttribute('aria-selected',String(b.dataset.tab===name));b.tabIndex=b.dataset.tab===name?0:-1;});
      ['map','clues','log'].forEach(t=>$('xp-panel-'+t).hidden=t!==name);message($('xp-global-message'),'');window.scrollTo(0,0);
      if(name==='clues')await loadClues();if(name==='log')await loadLog();
    }
    const tabs=[...document.querySelectorAll('[data-tab]')];tabs.forEach((b,i)=>{b.onclick=()=>tab(b.dataset.tab);b.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const n=e.key==='Home'?0:e.key==='End'?2:(i+(e.key==='ArrowRight'?1:2))%3;tabs[n].focus();tab(tabs[n].dataset.tab);}};});
    document.addEventListener('visibilitychange',()=>{if(!document.hidden&&active==='log')loadLog();});
    $('xp-clue-search').oninput=renderClues;document.querySelectorAll('#xp-clue-view button').forEach(b=>b.onclick=()=>{clueView=b.dataset.view;renderClues();});$('xp-reload-state').onclick=loadState;$('xp-reload-log').onclick=loadLog;
    $('xp-sheet-close').onclick=()=>sheet.close();sheet.addEventListener('click',e=>{if(e.target===sheet){const r=sheet.getBoundingClientRect();if(e.clientY<r.top||e.clientX<r.left||e.clientX>r.right)sheet.close();}});
    $('xp-visit').onclick=async()=>{
      if(visiting||!currentSpot||exhausted)return;
      visiting=true;updateVisitButton();message($('xp-sheet-message'),'');const spot=currentSpot;
      try {
        const data=await request('/x/api/visit',{spot_id:spot.id});quota(data.quota);
        if(data.kind==='clue'){state.clue_new=(state.clue_new||0)+1;badge(state.clue_new);}
        if(currentSpot?.id===spot.id){
          const result=$('xp-visit-result');result.hidden=false;
          const labels={clue:'发现线索',item:'获得物品',nothing:'这次空手而归',empty:'没有新发现'};
          const hints={clue:'已收入线索板',item:'入包中，稍等片刻',nothing:'这一步也记在了手账里。',empty:'这次没有扣次数，可以去别处看看。'};
          result.innerHTML=`<span class="xp-eyebrow">${labels[data.kind]||'探索结果'}</span><h3>${esc(data.kind==='empty'?'这里没有新发现了':data.title)}</h3>${data.text?`<p>${esc(data.text)}</p>`:''}<p class="xp-hint">${hints[data.kind]||''}</p>`;
          exhausted=data.kind==='empty';result.scrollIntoView({block:'nearest'});
        }
        if(!sheet.open)message($('xp-global-message'),`探索完成：${data.title}。在记录里可以查看。`);
      } catch(err){if(err.data?.quota)quota(err.data.quota);if(err.status===403&&state)state.enabled=false;fail(sheet.open?$('xp-sheet-message'):$('xp-global-message'),err);}
      finally{visiting=false;updateVisitButton();}
    };
    $('xp-logout').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget,body=new FormData(form);await lock(form,async()=>{try{const res=await fetch(form.action,{method:'POST',body,credentials:'same-origin'});if(!res.ok)throw new Error();location.assign('/x');}catch(_){message($('xp-global-message'),'退出没有完成，请稍后重试。',true);}});};
    loadState();return;
  }
  // Administration: keep an unsaved spot draft intact when unrelated settings change.
  let state=null, selectedMap='', selectedSpot='', editorDirty=false, logs=[], dropSerial=0;
  const selectedRoles=new Set(), form=$('xp-spot-form'), mapSelect=$('xp-edit-map'), spotSelect=$('xp-edit-spot');
  const field=name=>form.elements.namedItem(name);
  const getMap=()=>state?.maps.find(m=>String(m.id)===selectedMap);
  function ask(text,title='确认删除',label='确认删除') {
    const dialog=$('xp-confirm');$('xp-confirm-title').textContent=title;$('xp-confirm-text').textContent=text;
    const yes=dialog.querySelector('[data-confirm-yes]'),no=dialog.querySelector('[data-confirm-cancel]');yes.textContent=label;
    return new Promise(resolve=>{let result=false;yes.onclick=()=>{result=true;dialog.close();};no.onclick=()=>dialog.close();dialog.addEventListener('close',()=>resolve(result),{once:true});dialog.showModal();no.focus();});
  }
  async function abandon() {return !editorDirty || await ask('这个地点还有未保存的修改。切换后会放下这些修改。','切换编辑地点？','放下并切换');}
  async function save(container,path,body,after) {
    const box=feedback(container)||$('xp-global-message');let success=false;
    await lock(container,async()=>{
      message(box,'正在保存…');
      try {
        const result=await request('/admin/explore/api/'+path,body);success=true;
        message(box,result.warn||'已保存。');
        // A successful write must remain distinguishable from a failed follow-up read.
        try {await refresh({settings:path==='settings'});if(after)await after(result);}
        catch(err){message(box,'已保存，但最新状态暂时没读到。可重新读取配置，不必重复提交。',true);$('xp-admin-reload').hidden=false;}
      } catch(err){fail(box,err);}
    });
    // lock restores the original states; apply dynamic restrictions once more.
    updateDropAvailability();return success;
  }
  function options(rows,value,placeholder) {return (placeholder?`<option value="">${esc(placeholder)}</option>`:'')+rows.map(r=>`<option value="${esc(r.id)}"${String(r.id)===String(value)?' selected':''}>${esc(r.name)}</option>`).join('');}
  function settingsView() {
    const f=$('xp-settings-form');f.elements.enabled.checked=state.settings.enabled;f.elements.default_daily.value=state.settings.default_daily;f.elements.reset_hour.value=state.settings.reset_hour;f.elements.intro.value=state.settings.intro||'';
  }
  function drawPosition() {
    const map=getMap(), art=$('xp-position-art');$('xp-position-map').classList.toggle('has-image',!!map?.image);
    if(art.dataset.image!==(map?.image||'')) {art.dataset.image=map?.image||'';art.innerHTML=map?.image?`<img src="${esc(map.image)}" alt="${esc(map.name)}，点击设置地点位置">`:'';art.querySelector('img')?.addEventListener('error',()=>{art.replaceChildren();message(feedback(form),'地图图片暂时无法显示，可以先用下方坐标设置位置。',true);});}
    const pin=$('xp-position-pin');pin.style.setProperty('--pin-x',(Number(field('x').value)||0)+'%');pin.style.setProperty('--pin-y',(Number(field('y').value)||0)+'%');pin.firstElementChild.textContent=field('icon').value||'📍';
  }
  function renderSelectors() {
    if(!state.maps.some(m=>String(m.id)===selectedMap)) {selectedMap=state.maps[0]?String(state.maps[0].id):'';selectedSpot='';editorDirty=false;}
    mapSelect.innerHTML=options(state.maps,selectedMap,state.maps.length?null:'先添加地图');
    const map=getMap();spotSelect.innerHTML=options((map?.spots||[]).map(s=>({id:s.id,name:s.name+(!s.enabled&&s.x===50&&s.y===50?' · 待定位':'')})),selectedSpot,'＋ 新建地点');
    mapSelect.disabled=!map;spotSelect.disabled=!map;
    if(!map){form.hidden=true;}else form.hidden=false;
    drawPosition();
  }
  function probabilities() {
    const rows=[...$('xp-drop-rows').children], weights=rows.map(r=>Math.max(0,Number(r.querySelector('[data-field=weight]').value)||0)), total=weights.reduce((a,b)=>a+b,0);
    rows.forEach((r,i)=>{r.querySelector('.xp-probability').innerHTML=`${total?(weights[i]/total*100).toLocaleString('zh-CN',{maximumFractionDigits:1}):'0'}% <small>概率</small>`;});
    $('xp-drop-count').textContent=rows.length+' / 30 项';$('xp-add-drop').disabled=rows.length>=30;
  }
  function itemOptions(value) {
    const groups=state.items||[], exists=groups.some(g=>g.names.includes(value));
    return '<option value="">选择注册物品</option>'+(!exists&&value?`<option value="${esc(value)}" selected disabled>${esc(value)}（已不在清单，请重选）</option>`:'')+groups.map(g=>`<optgroup label="${esc(g.group)}">${g.names.map(name=>`<option value="${esc(name)}"${name===value?' selected':''}>${esc(name)}</option>`).join('')}</optgroup>`).join('');
  }
  function updateDropAvailability() {
    if(!state)return;
    const can=!!state.plugin.can_items, has=(state.items||[]).some(g=>g.names.length);
    $('xp-plugin-note').textContent=!can?'插件版本太旧，发不出去。可先配置线索或空手掉落。':!has?'还没有同步到物品清单。等机器人同步后再选物品。':'物品只从已注册清单中选择，抽到后由机器人自动放入背包。';
    $('xp-plugin-note').classList.toggle('is-error',!can);
    $('xp-drop-rows').querySelectorAll('[data-field=kind] option[value=item]').forEach(o=>o.disabled=!can||!has);
    probabilities();
  }
  function dropFields(row,values) {
    const kind=row.querySelector('[data-field=kind]').value, box=row.querySelector('.xp-drop-fields');
    if(kind==='clue')box.innerHTML=`<label>线索标题<input data-field="title" maxlength="30" required value="${esc(values.title||'')}"></label><label>线索内容<textarea data-field="text" maxlength="600" required>${esc(values.text||'')}</textarea></label>`;
    else if(kind==='item')box.innerHTML=`<div class="xp-two"><label>注册物品<select data-field="item" required>${itemOptions(values.item||'')}</select></label><label>数量<input data-field="qty" type="number" min="1" max="999" value="${esc(values.qty||1)}" required></label></div><label>掉落描述（选填）<textarea data-field="text" maxlength="200">${esc(values.text||'')}</textarea></label>`;
    else box.innerHTML=`<label>空手时的一句话（选填）<textarea data-field="text" maxlength="200">${esc(values.text||'')}</textarea></label>`;
  }
  function addDrop(data={kind:'clue',weight:1}) {
    if($('xp-drop-rows').children.length>=30)return;
    const row=document.createElement('div');row.className='xp-drop';row.dataset.serial=String(++dropSerial);if(data.id)row.dataset.dropId=data.id;
    row.innerHTML=`<div class="xp-drop-head"><span class="xp-probability"></span><button type="button" class="xp-icon-btn xp-danger" data-remove-drop aria-label="移除这条掉落">×</button></div><div class="xp-two"><label>掉落类型<select data-field="kind"><option value="clue">线索</option><option value="item">物品</option><option value="nothing">空手</option></select></label><label>权重<input data-field="weight" type="number" min="1" max="1000" value="${esc(data.weight||1)}" required></label></div><div class="xp-drop-fields"></div>`;
    row.querySelector('[data-field=kind]').value=data.kind;dropFields(row,data);
    row.querySelector('[data-field=kind]').onchange=()=>{dropFields(row,{});editorDirty=true;};
    row.querySelector('[data-remove-drop]').onclick=()=>{row.remove();editorDirty=true;probabilities();};
    row.querySelector('[data-field=weight]').oninput=probabilities;$('xp-drop-rows').append(row);updateDropAvailability();
  }
  function readDrops() {
    return [...$('xp-drop-rows').children].map(row=>{
      const out={};if(row.dataset.dropId)out.id=row.dataset.dropId;
      row.querySelectorAll('[data-field]').forEach(c=>{out[c.dataset.field]=['weight','qty'].includes(c.dataset.field)?Number(c.value):c.value;});return out;
    });
  }
  function loadSpot(spotId='') {
    selectedSpot=String(spotId||'');const spot=getMap()?.spots.find(s=>String(s.id)===selectedSpot);
    field('id').value=spot?.id||'';field('name').value=spot?.name||'';field('icon').value=spot?.icon||'📍';field('desc').value=spot?.desc||'';field('x').value=spot?.x??50;field('y').value=spot?.y??50;field('enabled').checked=spot?spot.enabled:true;
    $('xp-drop-rows').replaceChildren();(spot?.drops||[]).forEach(addDrop);$('xp-delete-spot').hidden=!spot;spotSelect.value=selectedSpot;
    editorDirty=false;message(feedback(form),'');drawPosition();updateDropAvailability();
  }
  function renderMaps() {
    $('xp-admin-maps').innerHTML=state.maps.length?state.maps.map(m=>`<article class="xp-map-edit" data-map-card="${m.id}"><form data-map-rename="${m.id}" class="xp-inline-form"><label>地图名称<input name="name" maxlength="30" value="${esc(m.name)}" required></label><button type="submit" class="xp-button xp-quiet">改名</button><p class="xp-message" data-feedback role="status" hidden></p></form>${m.image?`<img src="${esc(m.image)}" alt="${esc(m.name)}地图预览">`:'<p class="xp-empty">未上传背景图<br>玩家将看到地点列表</p>'}<p class="xp-hint">${m.spots.length} 个地点 · 图片不超过 12 MB</p><label class="xp-upload">上传／替换背景图<input data-map-upload="${m.id}" type="file" accept="image/jpeg,image/png,image/webp"></label><p class="xp-message" data-feedback role="status" hidden></p><button type="button" class="xp-button xp-danger" data-map-delete="${m.id}">删除地图</button></article>`).join(''):'<p class="xp-empty">还没有地图，从一个名字开始吧。</p>';
  }
  function renderRoles() {
    const roles=state.roles||[], valid=new Set(roles.map(r=>r.role));for(const r of selectedRoles)if(!valid.has(r))selectedRoles.delete(r);
    $('xp-role-list').innerHTML=roles.length?roles.map(r=>`<label class="xp-role"><input type="checkbox" data-role="${esc(r.role)}"${selectedRoles.has(r.role)?' checked':''}><span>${esc(r.role)}<small>每天 ${esc(r.daily_limit)} 次${r.custom?' · 自定义':' · 跟随默认'}</small></span><span>已用 ${esc(r.used_today)} · 剩 ${esc(r.left_today)}<small>临时 ${esc(r.bonus)} 次</small></span></label>`).join(''):'<p class="xp-empty">还没有角色，等角色同步后再分配次数。</p>';
    updateSelected();const select=$('xp-log-role'),old=select.value;select.innerHTML='<option value="">全部角色</option>'+roles.map(r=>`<option value="${esc(r.role)}">${esc(r.role)}</option>`).join('');select.value=old;
  }
  function updateSelected() {
    $('xp-selected-count').textContent=selectedRoles.size?'已选 '+selectedRoles.size+' 人':'未选角色';const all=$('xp-select-all'),n=state.roles.length;all.checked=n>0&&selectedRoles.size===n;all.indeterminate=selectedRoles.size>0&&selectedRoles.size<n;all.disabled=!n;
  }
  function renderLogs() {const role=$('xp-log-role').value;$('xp-admin-log').innerHTML=logHTML(logs.filter(r=>!role||r.role===role),true);}
  async function loadLogs() {
    const b=$('xp-admin-log-reload');b.disabled=true;
    try{logs=(await request('/admin/explore/api/log')).log;renderLogs();}
    catch(err){fail($('xp-global-message'),err);}
    finally{b.disabled=false;}
  }
  async function refresh(opts={}) {
    state=await request('/admin/explore/api/state');
    if(opts.settings)settingsView();$('xp-admin-day').textContent='计数日 '+state.day;
    renderMaps();renderRoles();renderSelectors();updateDropAvailability();
    $('xp-admin-workspace').hidden=false;$('xp-admin-reload').hidden=true;
  }
  $('xp-settings-form').onsubmit=e=>{e.preventDefault();const f=e.currentTarget;save(f,'settings',{enabled:f.elements.enabled.checked,default_daily:Number(f.elements.default_daily.value),reset_hour:Number(f.elements.reset_hour.value),intro:f.elements.intro.value});};
  $('xp-new-map').onsubmit=e=>{e.preventDefault();const f=e.currentTarget;save(f,'map',{name:f.elements.name.value},res=>{f.reset();if(!editorDirty){selectedMap=String(res.id);selectedSpot='';renderSelectors();loadSpot();}message($('xp-global-message'),'地图已添加，可以上传背景图或配置地点。');});};
  $('xp-admin-maps').addEventListener('submit',e=>{const f=e.target.closest('[data-map-rename]');if(!f)return;e.preventDefault();save(f,'map',{id:Number(f.dataset.mapRename),name:f.elements.name.value},()=>message($('xp-global-message'),'地图已改名。'));});
  $('xp-admin-maps').addEventListener('change',async e=>{
    const input=e.target.closest('[data-map-upload]');if(!input||!input.files[0])return;const file=input.files[0],card=input.closest('.xp-map-edit'),box=card.querySelector(':scope > [data-feedback]');
    if(file.size>12*1024*1024){message(box,'图片不能超过 12 MB，换一张小一点的吧。',true);input.value='';return;}
    const body=new FormData();body.append('image',file);await save(card,`map/${input.dataset.mapUpload}/image`,body,()=>message($('xp-global-message'),'地图图片已更新。'));
  });
  $('xp-admin-maps').addEventListener('click',async e=>{
    const b=e.target.closest('[data-map-delete]');if(!b)return;const id=Number(b.dataset.mapDelete),map=state.maps.find(m=>m.id===id);
    if(!await ask(`删除「${map.name}」？这张地图和它的 ${map.spots.length} 个地点都会被删除。`))return;
    await save(b.closest('.xp-map-edit'),'map/delete',{id},()=>{if(selectedMap===String(id)||!editorDirty)loadSpot();message($('xp-global-message'),'地图已删除。');});
  });
  mapSelect.onchange=async()=>{const next=mapSelect.value;mapSelect.value=selectedMap;if(form.dataset.busy||!await abandon())return;selectedMap=next;selectedSpot='';editorDirty=false;renderSelectors();loadSpot();};
  spotSelect.onchange=async()=>{const next=spotSelect.value;spotSelect.value=selectedSpot;if(form.dataset.busy||!await abandon())return;loadSpot(next);};
  form.addEventListener('input',()=>{editorDirty=true;drawPosition();});form.addEventListener('change',()=>{editorDirty=true;});
  $('xp-add-drop').onclick=()=>{addDrop();editorDirty=true;};
  form.onsubmit=e=>{
    e.preventDefault();const map=getMap();if(!map)return;
    const data={map_id:map.id,name:field('name').value,icon:field('icon').value,desc:field('desc').value,x:Number(field('x').value),y:Number(field('y').value),enabled:field('enabled').checked,drops:readDrops()};if(field('id').value)data.id=Number(field('id').value);
    save(form,'spot',data,res=>{selectedSpot=String(res.id);renderSelectors();loadSpot(res.id);message(feedback(form),res.warn||'地点与掉落已保存。');});
  };
  $('xp-delete-spot').onclick=async()=>{if(!field('id').value)return;const id=Number(field('id').value);if(await ask(`删除「${field('name').value}」和它的掉落表？`))await save(form,'spot/delete',{id},()=>{selectedSpot='';renderSelectors();loadSpot();message(feedback(form),'地点已删除。');});};
  const position=$('xp-position-map'),pin=$('xp-position-pin');let dragging=false;
  function put(e) {const r=position.getBoundingClientRect();field('x').value=(Math.max(0,Math.min(100,(e.clientX-r.left)/r.width*100))).toFixed(1);field('y').value=(Math.max(0,Math.min(100,(e.clientY-r.top)/r.height*100))).toFixed(1);editorDirty=true;drawPosition();}
  position.addEventListener('click',e=>{if(!form.dataset.busy)put(e);});
  pin.addEventListener('pointerdown',e=>{if(form.dataset.busy)return;dragging=true;pin.setPointerCapture(e.pointerId);});
  pin.addEventListener('pointermove',e=>{if(dragging)put(e);});
  ['pointerup','pointercancel','lostpointercapture'].forEach(name=>pin.addEventListener(name,()=>{dragging=false;}));
  pin.addEventListener('keydown',e=>{const moves={ArrowLeft:['x',-1],ArrowRight:['x',1],ArrowUp:['y',-1],ArrowDown:['y',1]};if(moves[e.key]){e.preventDefault();const [key,n]=moves[e.key];field(key).value=Math.max(0,Math.min(100,Number(field(key).value)+n));editorDirty=true;drawPosition();}});
  $('xp-select-all').onchange=e=>{state.roles.forEach(r=>{if(e.target.checked)selectedRoles.add(r.role);else selectedRoles.delete(r.role);});renderRoles();};
  $('xp-role-list').addEventListener('change',e=>{const input=e.target.closest('[data-role]');if(!input)return;if(input.checked)selectedRoles.add(input.dataset.role);else selectedRoles.delete(input.dataset.role);updateSelected();});
  const qform=$('xp-quota-form');qform.elements.action.onchange=()=>{
    const action=qform.elements.action.value,amount=qform.elements.amount;$('xp-quota-amount-label').hidden=action==='default';amount.disabled=action==='default';$('xp-quota-note-label').hidden=action!=='bonus';
    $('xp-quota-amount-label').firstElementChild.textContent=action==='bonus'?'临时次数（负数为扣除）':'每天次数';amount.min=action==='bonus'?'-99':'0';amount.max='99';amount.value=action==='bonus'?'1':'3';
    $('xp-quota-hint').textContent=action==='default'?'选中的角色将重新跟随默认次数。':action==='bonus'?'正数增加，负数扣除；临时次数不过期。':'会应用到所有选中的角色。';
  };
  qform.onsubmit=e=>{e.preventDefault();if(!selectedRoles.size){message(feedback(qform),'先选至少一个角色。',true);return;}const action=qform.elements.action.value,n=Number(qform.elements.amount.value);if(action==='bonus'&&n===0){message(feedback(qform),'临时次数不能是 0。',true);return;}const roles=[...selectedRoles],body=action==='bonus'?{roles,amount:n,note:qform.elements.note.value}:{roles,daily:action==='default'?null:n};save(qform,action==='bonus'?'bonus':'quota',body,()=>message(feedback(qform),`已更新 ${roles.length} 位角色的次数。`));};
  $('xp-log-role').onchange=renderLogs;$('xp-admin-log-reload').onclick=loadLogs;
  $('xp-admin-reload').onclick=async()=>{try{const initial=!state;await refresh({settings:initial});if(initial)loadSpot();message($('xp-global-message'),'配置已更新，正在编辑的地点内容已保留。');}catch(err){fail($('xp-global-message'),err);}};
  // 批量导入 / 导出（文本）与批量设置次数：先预览，再提交；预览之后文本或选项改了，就要重新预览
  const impText=$('xp-import-text'), impMsg=$('xp-import-msg'), impBox=$('xp-import-result'), impPanel=$('xp-import');
  const conflict=()=>document.querySelector('input[name=xp-conflict]:checked').value;
  let impKey='';const impSig=()=>conflict()+'\n'+impText.value;
  function impButtons(){const good=impKey&&impKey===impSig();$('xp-import-commit').disabled=!good;$('xp-conflict-warn').hidden=conflict()!=='replace';}
  function sampleText() {
    const item=(state.items||[]).flatMap(g=>g.names)[0];
    return ['# 地图：学院','@图书馆 📚 x=20 y=28 | 安静得能听见翻页声。','线索 5 | 撕碎的信 | 信纸被撕成两半，只剩半句：「别让他知道……」\\n（内容里换行写 \\n）',item?`物品 2 | ${item} ×1 | 压在书页里。`:'// 物品 2 | 注册过的物品名 ×1','空手 2 | 只有灰尘。','','@钟楼 🔔 | 没写 x、y：先停用，等你在图上点选位置','线索 4 | 停摆的怀表 | 怀表停在 21:07。','空手 3',''].join('\n');
  }
  function jumpToLine(n) {
    if(!n)return;const lines=impText.value.split('\n');let start=0;for(let i=0;i<n-1&&i<lines.length;i++)start+=lines[i].length+1;
    impText.focus();impText.setSelectionRange(start,start+(lines[n-1]||'').length);
    const lh=parseFloat(getComputedStyle(impText).lineHeight)||20;impText.scrollTop=Math.max(0,(n-3)*lh);
  }
  function errorsHTML(errors,more) {
    return `<ul class="xp-errors">${errors.map(e=>`<li>${e.line?`<button type="button" class="xp-button xp-quiet" data-line="${e.line}">${esc(e.msg)}</button>`:esc(e.msg)}</li>`).join('')}</ul>${more?`<p class="xp-hint">还有 ${more} 处错误没有列出，先改上面这些。</p>`:''}`;
  }
  const TAGS={create:'新建',replace:'覆盖',skip:'跳过'};
  function planHTML(res) {
    const s=res.summary;
    return `<p class="xp-summary">新增地图 ${s.maps_new} · 新建地点 ${s.spots_create} · 覆盖 ${s.spots_replace} · 跳过 ${s.spots_skip} · 共 ${s.drops_total} 条掉落</p><ul class="xp-plan">${res.plan.map(p=>`<li><span class="xp-tag ${p.action}">${TAGS[p.action]}</span> <b>${esc(p.map)}${p.map_new?'（新地图）':''} · ${esc(p.spot)}</b>${p.action==='skip'?'<small>已有同名地点，保持不变</small>':`<small>${p.drops} 条掉落${p.items.length?' · '+esc(p.items.join('、')):''}</small>`}${p.action==='create'&&!p.has_pos?'<span class="xp-tag pending">待定位</span>':''}</li>`).join('')}</ul>`;
  }
  async function impRun(mode) {
    await lock(impPanel,async()=>{
      message(impMsg,mode==='commit'?'正在导入…':'正在检查…');impBox.innerHTML='';
      try {
        const sig=impSig(), res=await request('/admin/explore/api/import',{text:impText.value,mode,on_conflict:conflict()});
        if(res.errors.length){message(impMsg,`有 ${res.errors.length+(res.more||0)} 处错误，改好再预览。点一条可跳到那一行。`,true);impBox.innerHTML=errorsHTML(res.errors,res.more);impKey='';return;}
        impBox.innerHTML=planHTML(res);
        if(mode==='preview'){impKey=sig;message(impMsg,'检查通过，确认计划无误后点「导入」。');return;}
        impKey='';
        let note=`导入完成：新建 ${res.summary.spots_create} 个地点，覆盖 ${res.summary.spots_replace} 个。`;
        if(res.pending_pos)note+=` 其中 ${res.pending_pos} 个新地点还没有位置，请在上面的图上点选位置并开放。`;
        try{await refresh();note+='';}catch(e){note+=' 但最新配置暂时没读到，请点「重新读取配置」。';$('xp-admin-reload').hidden=false;}
        message(impMsg,note);
      } catch(err){fail(impMsg,err);impKey='';}
    });
    impButtons();
  }
  impText.addEventListener('input',impButtons);
  document.querySelectorAll('input[name=xp-conflict]').forEach(r=>r.onchange=impButtons);
  impBox.addEventListener('click',e=>{const b=e.target.closest('[data-line]');if(b)jumpToLine(Number(b.dataset.line));});
  $('xp-import-preview').onclick=()=>impRun('preview');
  $('xp-import-commit').onclick=async()=>{
    if(conflict()==='replace'&&!await ask('同名地点的描述、图标和掉落表会被文本里的内容替换（位置和启用状态保留）。','覆盖同名地点？','确认覆盖'))return;
    impRun('commit');
  };
  $('xp-import-sample').onclick=async()=>{if(impText.value.trim()&&!await ask('文本框里现有的内容会被示例覆盖。','填入示例？','覆盖'))return;impText.value=sampleText();impKey='';impButtons();};
  $('xp-import-export').onclick=async()=>{
    if(impText.value.trim()&&!await ask('文本框里现有的内容会被当前配置覆盖。','导出当前配置？','覆盖'))return;
    await lock(impPanel,async()=>{try{const res=await request('/admin/explore/api/export');impText.value=res.text;impKey='';impBox.innerHTML='';message(impMsg,res.text?'已导出当前全部地图。可以改完再导入（同名地点选「覆盖」）。':'现在还没有任何地图和地点。');}catch(err){fail(impMsg,err);}});
    impButtons();
  };
  $('xp-import-copy').onclick=async()=>{
    try{await navigator.clipboard.writeText(impText.value);}catch(e){impText.focus();impText.select();try{document.execCommand('copy');}catch(_){message(impMsg,'复制失败，请手动全选复制。',true);return;}}
    message(impMsg,'已复制。');
  };
  const qText=$('xp-quota-text'), qMsg=$('xp-quota-msg'), qBox=$('xp-quota-result'), qPanel=$('xp-quota-import');let qKey='';
  function qButtons(){$('xp-quota-commit').disabled=!(qKey&&qKey===qText.value);}
  async function qRun(mode) {
    await lock(qPanel,async()=>{
      message(qMsg,mode==='commit'?'正在应用…':'正在检查…');qBox.innerHTML='';
      try {
        const key=qText.value,res=await request('/admin/explore/api/quota_import',{text:key,mode});
        if(res.errors.length){qKey='';message(qMsg,`有 ${res.errors.length} 处错误，改好再预览。`,true);qBox.innerHTML=errorsHTML(res.errors,0);return;}
        qBox.innerHTML=(res.default!=null?`<p class="xp-summary">默认每人每天 ${res.default} 次</p>`:'')+(res.warnings.length?`<p class="xp-hint">${res.warnings.map(esc).join('<br>')}</p>`:'')+`<ul class="xp-plan">${res.plan.map(p=>`<li><b>${esc(p.role)}</b> 每天 ${p.daily} 次 <span class="xp-tag ${p.change==='自定义'?'replace':'skip'}">${p.change}</span></li>`).join('')}</ul>`;
        if(mode==='preview'){qKey=key;message(qMsg,'检查通过，确认后点「应用」。');return;}
        qKey='';message(qMsg,'已应用。');
        try{await refresh();}catch(e){message(qMsg,'已应用，但最新配置暂时没读到，请点「重新读取配置」。',true);$('xp-admin-reload').hidden=false;}
      } catch(err){fail(qMsg,err);qKey='';}
    });
    qButtons();
  }
  qText.addEventListener('input',qButtons);qBox.addEventListener('click',e=>{const b=e.target.closest('[data-line]');if(!b)return;const n=Number(b.dataset.line),ls=qText.value.split('\n');let s=0;for(let i=0;i<n-1&&i<ls.length;i++)s+=ls[i].length+1;qText.focus();qText.setSelectionRange(s,s+(ls[n-1]||'').length);});
  $('xp-quota-preview').onclick=()=>qRun('preview');$('xp-quota-commit').onclick=()=>qRun('commit');
  window.addEventListener('beforeunload',e=>{if(editorDirty){e.preventDefault();e.returnValue='';}});
  // base.html owns the existing viewport element, so update it without adding a duplicate.
  document.querySelector('meta[name=viewport]')?.setAttribute('content','width=device-width,initial-scale=1,viewport-fit=cover');
  (async()=>{try{await refresh({settings:true});loadSpot();message($('xp-global-message'),'');await loadLogs();}catch(err){fail($('xp-global-message'),err);$('xp-admin-reload').hidden=false;}})();
}());
