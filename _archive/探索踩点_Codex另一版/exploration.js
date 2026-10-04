(function () {
  'use strict';
  var source = document.getElementById('exploreMaps');
  var maps = source ? JSON.parse(source.textContent) : {};
  var select = document.getElementById('exploreMapSelect'), stage = document.getElementById('exploreMap');
  function draw(target, name) {
    var cfg = maps[name], art = target.querySelector('.ex-map-art');
    art.innerHTML = cfg ? PlaceMap.render(cfg) : '';
    target.style.aspectRatio = cfg ? cfg.w + '/' + cfg.h : '';
  }
  if (select && stage) {
    function show() {
      draw(stage, select.value);
      stage.querySelectorAll('[data-map]').forEach(function (pin) { pin.hidden = pin.dataset.map !== select.value; });
    }
    var first = stage.querySelector('[data-map]');
    if (first) select.value = first.dataset.map;
    select.addEventListener('change', show); show();
  }
  document.querySelectorAll('[data-explore-visit]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (form.dataset.busy) { e.preventDefault(); return; }
      form.dataset.busy = '1';
      var button = form.querySelector('button'); button.disabled = true; button.textContent = '正在探索…';
    });
  });
  window.addEventListener('pageshow', function (e) { if (e.persisted) location.reload(); });
  document.querySelectorAll('[data-place-editor]').forEach(function (form) {
    var preview = form.querySelector('.ex-map'), mapSelect = form.querySelector('[name=map_name]');
    var pin = preview.querySelector('.ex-pin'), x = form.querySelector('[name=x]'), y = form.querySelector('[name=y]');
    function update() { draw(preview,mapSelect.value); pin.style.left=x.value+'%'; pin.style.top=y.value+'%'; }
    mapSelect.addEventListener('change',update);x.addEventListener('input',update);y.addEventListener('input',update);
    preview.addEventListener('click',function(e){var r=preview.getBoundingClientRect();x.value=Math.max(5,Math.min(95,Math.round((e.clientX-r.left)/r.width*100)));y.value=Math.max(5,Math.min(95,Math.round((e.clientY-r.top)/r.height*100)));update();});update();
  });
  document.querySelectorAll('[data-drop-editor]').forEach(function(form){
    var kind=form.querySelector('[name=kind]');
    function update(){form.querySelectorAll('[data-drop-kind]').forEach(function(box){box.hidden=box.dataset.dropKind==='item'?kind.value!=='item':kind.value==='item';box.querySelectorAll('input,select,textarea').forEach(function(input){input.disabled=box.hidden;});});}
    kind.addEventListener('change',update);update();
  });
}());
