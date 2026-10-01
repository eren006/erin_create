// 网页心愿的「顺序与冲突」测试：从源码里截出 摘心愿核心(wishPickCore / wishDecrDailyCount) 和 网页操作队列(phoneApplyWishOps 一组)，用桩环境跑。
// 用法：node 长日系统/tests/wish_web_order_test.js ，通过时打印 PICK OK / QUEUE OK
// 覆盖：两个人同时摘同一个只有一个成功且只建一次群 / 建群失败心愿放回+次数退回+不发奖励 / 操作按 id 先后一次一个、后面的操作等摘取建群完 /
//       重复下发不重复执行 / 已回报的不重跑 / 插件重载中途不自动重摘（报状态不明）
const fs = require("fs"), path = require("path");
const soc = fs.readFileSync(path.join(__dirname, "..", "长日社交.js"), "utf8");
const main = fs.readFileSync(path.join(__dirname, "..", "长日系统.js"), "utf8");
const slice = (src, a, b) => { const i = src.indexOf(a), j = src.indexOf(b, i); if (i < 0 || j < 0) throw new Error("截取失败：" + a); return src.slice(i, j); };
const PICK_SRC = slice(soc, "function wishDecrDailyCount", "function wishRemoveFromInv") + slice(soc, "async function wishPickCore", "let cmd_pick_wish = {};");
const QUEUE_SRC = slice(main, "const _wishOpsKnown = new Set();", "// 无前缀「短信」：识别署名");
async function runPick() {
  const code = `
const store={a_wishPool:[], wish_daily_pick_counts:{}, phone_wish_ops_done:[], phone_wish_ops_started:[]};
const clone=x=>JSON.parse(JSON.stringify(x));
const mainKvGet=(k,d)=>store[k]!==undefined?clone(store[k]):d, mainKvSet=(k,v)=>{store[k]=clone(v)};
const kvGet=mainKvGet, kvSet=mainKvSet;
const WishUtils={getPool:()=>mainKvGet("a_wishPool",[]),savePool:p=>mainKvSet("a_wishPool",p)};
const wishIsOwner=(pf,uid,raw,from)=>from===uid||from===raw;
const names={"QQ:1":"林晚","QQ:2":"周屿","QQ:3":"沈知意"};
const getUserRoleName=(pf,u)=>names[u]||null;
const checkAcceptanceConflicts=()=>[], getStorageInt=(k,d)=>d, cachedGet=()=>"D2";
const wishGetDailyCount=(u,d,t)=>{const r=(store.wish_daily_pick_counts[u]||{day:"",count:0});return r.day===d?r.count:0};
const wishIncrDailyCount=(u,d,t)=>{const r=store.wish_daily_pick_counts[u]||{day:"",count:0};store.wish_daily_pick_counts[u]={day:d,count:r.day===d?r.count+1:1}};
let gidResult="G100", gidDelay=20, gidCalls=0;
const finalizeGroupCreation=async()=>{gidCalls++; await new Promise(r=>setTimeout(r,gidDelay)); return gidResult};
const recordInteractionStat=()=>{}, applyMsgTemplate=()=>null;
const inv={}; const wishAddToInv=(u,c,n)=>{inv[u]=(inv[u]||0)+n};
const getRoleDetails=()=>({uid:null,gid:null});
const seal={newMessage:()=>({}),createTempCtx:()=>({}),replyToSender:()=>{}};
` + PICK_SRC + `const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
  const W={id:"W1",day:"D2",time:"14:00-15:00",place:"咖啡厅",content:"c",fromId:"QQ:2",timestamp:Date.now(),rewardCode:"ROSE",rewardName:"玫瑰",rewardCount:2};
  store.a_wishPool=[W];
  // (a) 两个人同时摘同一个：只有一个成功（认领发生在 await 之前）
  const [r1,r2]=await Promise.all([wishPickCore("QQ",1,"林晚","W1",{endPoint:{}},{},()=>{}), wishPickCore("QQ",3,"沈知意","W1",{endPoint:{}},{},()=>{})]);
  console.log(JSON.stringify([r1.ok,r1.msg.slice(0,12),r2.ok,r2.msg]));
  if(!(r1.ok&&!r2.ok&&/不存在|已过期/.test(r2.msg))) throw new Error("race: first must win");
  if(gidCalls!==1) throw new Error("group created twice");
  if(inv["QQ:1"]!==2||inv["QQ:3"]) throw new Error("reward only to winner");
  if(WishUtils.getPool().length) throw new Error("pool should be empty");
  // (b) 建群失败：心愿放回、次数退回、奖励不发
  store.a_wishPool=[W]; gidResult=false; inv["QQ:1"]=0; store.wish_daily_pick_counts={};
  const r3=await wishPickCore("QQ",1,"林晚","W1",{endPoint:{}},{},()=>{});
  console.log(JSON.stringify(r3));
  if(r3.ok||WishUtils.getPool().length!==1||wishGetDailyCount("QQ:1","D2","pick")!==0||inv["QQ:1"]) throw new Error("restore on failure");
  // (c) 放回后可以被再摘
  gidResult="G200"; const r4=await wishPickCore("QQ",3,"沈知意","W1",{endPoint:{}},{},()=>{}); if(!r4.ok||r4.gid!=="G200") throw new Error("re-pick after restore");
  // (d) 不能摘自己的
  store.a_wishPool=[W]; const r5=await wishPickCore("QQ",2,"周屿","W1",{endPoint:{}},{},()=>{}); if(r5.ok||WishUtils.getPool().length!==1) throw new Error("own wish");
  console.log("PICK OK");
})().catch(e=>{console.error("FAIL",e.message);process.exit(1)});
`;
  await new Function(code)();
}
async function runQueue() {
  const code = `
const store={phone_wish_ops_done:[],phone_wish_ops_started:[]};
const clone=x=>JSON.parse(JSON.stringify(x));
const kvGet=(k,d)=>store[k]!==undefined?clone(store[k]):d, kvSet=(k,v)=>{store[k]=clone(v)};
const log=[]; let active=0,maxActive=0;
globalThis.__changriWishWeb={
  post:(p,role,v)=>{log.push("post:"+v.tag+"@"+active); return {ok:true,wishId:"P"+v.tag}},
  withdraw:(p,role,id)=>({ok:true,wishId:id}),
  pick:async(p,role,id)=>{active++;maxActive=Math.max(maxActive,active);log.push("pick-start:"+id); await new Promise(r=>setTimeout(r,60)); log.push("pick-end:"+id); active--; return {ok:true,wishId:id,gid:"G1"}}
};
` + QUEUE_SRC + `const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
  const ops=[{id:3,role:"a",kind:"post",payload:JSON.stringify({tag:"after"})},{id:1,role:"a",kind:"pick",payload:JSON.stringify({wish_id:"X"})},{id:2,role:"b",kind:"pick",payload:JSON.stringify({wish_id:"Y"})}];
  phoneApplyWishOps("QQ",ops);
  phoneApplyWishOps("QQ",ops);   // 下一次同步又收到同样的（回报还没送达）：不能重复执行
  await sleep(300);
  console.log(JSON.stringify(log));
  if(JSON.stringify(log)!==JSON.stringify(["pick-start:X","pick-end:X","pick-start:Y","pick-end:Y","post:after@0"])) throw new Error("order: id order and one at a time, later post waits for in-flight pick");
  if(maxActive!==1) throw new Error("parallel");
  const done=kvGet("phone_wish_ops_done"); if(done.map(d=>d.id).join()!=="1,2,3") throw new Error("reports order "+done.map(d=>d.id));
  // 已回报（在 done 里）的再次下发不执行
  phoneApplyWishOps("QQ",[ops[1]]); await sleep(100); if(log.length!==5) throw new Error("reported op re-run");
  // 插件重载中途：started 里有、内存里没有 → 不重跑，报状态不明
  store.phone_wish_ops_started=[9]; store.phone_wish_ops_done=[];
  phoneApplyWishOps("QQ",[{id:9,role:"a",kind:"pick",payload:JSON.stringify({wish_id:"Z"})}]); await sleep(100);
  const d2=kvGet("phone_wish_ops_done"); console.log(JSON.stringify(d2));
  if(d2.length!==1||d2[0].ok||!/状态不明/.test(d2[0].msg)||log.includes("pick-start:Z")) throw new Error("started guard");
  console.log("QUEUE OK");
})().catch(e=>{console.error("FAIL",e.message);process.exit(1)});
`;
  await new Function(code)();
}
runPick().then(runQueue).catch(e => { console.error("FAIL", e.message); process.exit(1); });
