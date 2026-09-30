"""收藏只保存本机标识，覆盖存储不可用、空间不足、跨角色隔离和轮询后的按钮状态。"""
import json, os, re, subprocess, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import app as A
with A.app.test_request_context('/p/me'):
    html=A.render_template('_phone_tools.html', sid=901, owner='测试角色')
script=re.search(r'<script>(.*?)</script>',html,re.S).group(1)
js=r"""
const vm=require('node:vm'),assert=require('node:assert/strict');
const source=SOURCE,id='a'.repeat(32),key='phone:saved:[901,"测试角色"]';
function run(store={},blocked=false,full=false) {
 const button={dataset:{saveKey:id},attrs:{},setAttribute(k,v){this.attrs[k]=v;}},toast={};
 const events={},win={};
 const ctx={document:{
   getElementById:n=>n==='toolsToast'?toast:null,
   querySelectorAll:()=>[button],
   addEventListener:(n,fn)=>events[n]=fn
 },window:{addEventListener:(n,fn)=>win[n]=fn},location:{hash:''},
 localStorage:{
   getItem(k){if(blocked)throw Error();return store[k]??null;},
   setItem(k,v){if(full)throw Error();store[k]=v;}
 },clearTimeout(){},setTimeout(){return 1;}};
 vm.createContext(ctx);vm.runInContext(source,ctx);
 return {button,toast,events,win,store,click(){events.click({target:{closest:()=>button}});}};
}
let x=run(); x.click();
assert.equal(x.button.attrs['aria-pressed'],'true');
assert.deepEqual(JSON.parse(x.store[key]),[id]);
assert.equal(Object.keys(x.store).length,1); // 没有消息正文、发件人或远端写入
x.events['phone:updated']();assert.equal(x.button.attrs['aria-pressed'],'true');
x=run(x.store);assert.equal(x.button.attrs['aria-pressed'],'true');
x.click();assert.deepEqual(JSON.parse(x.store[key]),[]);
x=run({},true);x.click();
assert.equal(x.button.attrs['aria-pressed'],'false');assert.match(x.toast.textContent,/无法保存/);
x=run({},false,true);x.click();
assert.equal(x.button.attrs['aria-pressed'],'false');assert.match(x.toast.textContent,/没有保存成功/);
x=run({'phone:saved:[902,"测试角色"]':JSON.stringify([id])});
assert.equal(x.button.attrs['aria-pressed'],'false');
x=run({[key]:'["invalid",null,123]'});assert.equal(x.button.attrs['aria-pressed'],'false');
x.store[key]=JSON.stringify([id]);x.win.storage({key});assert.equal(x.button.attrs['aria-pressed'],'true');
console.log('SAVED OK');
""".replace('SOURCE',json.dumps(script,ensure_ascii=False))
subprocess.run(['node','-e',js],check=True)
