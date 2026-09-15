/* 构建：把 src 合并成单个 index.html，输出到 build/index.html */
const fs = require('fs'), path = require('path');
const R = (p) => fs.readFileSync(path.join(__dirname, p), 'utf8');

const JS = ['src/engine.js', 'src/story/prologue.js', 'src/story/ch1.js',
            'src/story/ch2.js', 'src/ui.js'];

const html = `<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<title>云京弃子</title>
<style>
${R('src/style.css')}
</style>

<div id="stage">
  <div id="hud"></div>
  <div id="scroll"></div>
  <div id="choices"></div>

  <div id="tools"><button id="btn-profile">生 平</button></div>
  <div id="modal"></div>

  <div id="title">
    <div class="main">云京弃子</div>
    <div class="sub">测灵之日，有人在石上动了手脚</div>
    <button id="btn-new">新 的 一 世</button>
    <button id="btn-continue">续 前 缘</button>
    <div class="foot">存档保存在本机浏览器</div>
  </div>
</div>

<script>
${JS.map(f => '/* ===== ' + f + ' ===== */\n' + R(f)).join('\n\n')}
</script>
`;

fs.mkdirSync(path.join(__dirname, 'build'), { recursive: true });
fs.writeFileSync(path.join(__dirname, 'build/index.html'), html);
const kb = (Buffer.byteLength(html) / 1024).toFixed(1);
console.log('build/index.html  ' + kb + ' KB');
