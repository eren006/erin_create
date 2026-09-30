"""本机外观逻辑回归：不访问数据库，Node 内置 vm 模拟存储失败和列表刷新。"""
import json
import re
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as A

with A.app.test_request_context("/p/me"):
    html = A.render_template("phone.html", mode="inbox", sid=901, owner="测试角色",
                             threads=[], status={"can": False}, revision="", public=None)
script = html[html.index("  var scope ="):html.index("  function readKey(other)")]
harness = r"""
const vm = require('node:vm'), assert = require('node:assert/strict');
const source = SOURCE;
function row(name, classes=[]) {
  const flags = new Set(classes);
  return {dataset:{other:name}, classList:{
    contains:n=>flags.has(n), toggle:(n,on)=>on?flags.add(n):flags.delete(n)
  }};
}
function run(store={}, blocked=false) {
  let rows=[row('新联系人'), row('旧联系人'), row('__public__',['public-row'])];
  const phone={style:{setProperty(k,v){this[k]=v;}},dataset:{}};
  const list={querySelectorAll:()=>rows,appendChild(r){rows=rows.filter(x=>x!==r);rows.push(r);}};
  const ctx={document:{querySelector:()=>phone,querySelectorAll:()=>[],
    getElementById:id=>id==='inbox'?list:null,addEventListener(){}},
    window:{addEventListener(){}},
    localStorage:{getItem(k){if(blocked)throw Error('blocked');return store[k]??null;}},
    console};
  vm.createContext(ctx); vm.runInContext(source,ctx);
  return {ctx,phone,rows:()=>rows};
}
let x=run({},true);
assert.equal(x.phone.style['--mine'],'#6854bc');
assert.equal(x.phone.dataset.wall,'default');
assert.equal(x.phone.style['--reading-size'],'16px');
x=run({'phone:appearance:[901,"测试角色"]':'{"theme":"blue","wall":"mist"}',
       'phone:pins:[901,"测试角色"]':'["旧联系人"]'});
assert.equal(x.phone.style['--mine'],'#3267a8');
assert.equal(x.phone.dataset.wall,'mist');
assert.deepEqual(x.rows().map(r=>r.dataset.other),['__public__','旧联系人','新联系人']);
// 模拟轮询带来新节点，置顶要重新应用。
x.rows().forEach(r=>{delete r.dataset.order; r.classList.toggle('pinned',false);});
x.ctx.applyPersonal();
assert.equal(x.rows()[1].dataset.other,'旧联系人');
for(const value of ['null','[]','"bad"','{bad','{"theme":"__proto__","wall":"missing"}']){
  x=run({'phone:appearance:[901,"测试角色"]':value});
  assert.equal(x.phone.style['--mine'],'#6854bc');
  assert.equal(x.phone.dataset.wall,'default');
}
x=run({'phone:appearance:[901,"测试角色"]':'{"font":"large"}'});
assert.equal(x.phone.style['--reading-size'],'19px');
x=run({'phone:appearance:[901,"测试角色"]':'{"font":"999px"}'});
assert.equal(x.phone.style['--reading-size'],'16px');
// 其他季度/角色的偏好不串进来。
x=run({'phone:appearance:[902,"测试角色"]':'{"theme":"green","wall":"sage"}'});
assert.equal(x.phone.style['--mine'],'#6854bc');
for(const hex of Object.values(x.ctx.themes)){
  const rgb=hex.slice(1).match(/../g).map(v=>parseInt(v,16)/255)
    .map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
  const lum=rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
  assert.ok(1.05/(lum+.05)>=4.5,hex+' white contrast');
}
console.log('UI OK');
""".replace("SOURCE", json.dumps(script, ensure_ascii=False))
subprocess.run(["node", "-e", harness], check=True)
