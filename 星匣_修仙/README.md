# 云京弃子

橙光式单机修仙文字游戏。纯静态，零运行成本，上传星匣的是 `build/index.html` 一个文件。

## 目录

```
src/style.css          样式
src/engine.js          引擎：境界表 / 数值结算 / 明骰判定 / 存档
src/ui.js              渲染：场景机 / HUD / 选项 / 生平面板
src/story/prologue.js  楔子 · 云京
src/story/ch1.js       第一章 · 安身立命
src/story/ch2.js       第二章 · 登云梯
build/index.html       ← 上传这个（合并后的单文件）
云京弃子_主指令.md      世界观与人物设定圣经，续写时照它写
```

## 三条命令

```bash
node build.js      # 合并成 build/index.html
node check.js      # 检查场景断链、死胡同、无人抵达
node simulate.js   # 随机通关 400 次，验证无死循环 + 数值分布
```

改完剧情，这三条依次跑一遍再上传。

## 怎么加剧情

一个场景就是一次 `S(id, {...})`：

```js
S('c3_xxx', {
  title: '第三章 · 外门风波',      // 可选，居中金色小标题
  onEnter: { months: 2, exp: 100 }, // 进场即结算
  text: [
    '普通叙述段，自动首行缩进',
    ['talk',  '「对白，不缩进，稍亮」'],
    ['aside', '心声/旁白，小一号，偏灰'],
  ],
  choices: [
    { t: '选项文字',
      hint: '<span class="cost">心境 -5</span>　<span class="gain">但保住差事</span>',
      eff: { mind: -5, stones: 10, items: {'丹药': 1}, npc: {'陈瞎子': 5}, flags: {kk: true} },
      to: 'c3_yyy' },

    { t: '需要条件才能选的',
      cond: (s) => s.stones >= 50,
      lock: '（灵石不足）',            // 条件不满足时显示的灰字
      to: 'c3_zzz' },

    { t: '带判定的',
      roll: { label: '潜入', dc: 60,
        base: (s) => 20 + s.wits * 5,
        bonus: [
          (s) => s.flags.master_chen ? ['师父教过', 12] : null,
          ['夜色掩护', 15],
        ] },
      win: 'c3_win', lose: 'c3_lose' },
  ],
});
```

- 没有 `choices` 就写 `next: '下一幕'`，渲染成「继续」按钮。
- 文本里可用 `{name}` `{realm}` `{ta}` 插值 —— **境界一律用 `{realm}`，不要写死"炼气三层"**，否则数值一变就穿帮。
- 新增章节文件后，记得加进 `build.js` 的 `JS` 数组和 `check.js`、`simulate.js` 的文件列表。

## 两个已经踩过的坑

1. **正文里不要用英文直引号 `"`**，用 `「」`——JS 单引号字符串里会截断，而且中文排版难看。（`class="cost"` 这种 HTML 属性不受影响。）
2. **滚动要用 `scrollTo({behavior:'instant'})`**，不能用 `scrollTop = x`——浏览器默认 `scroll-behavior: smooth` 会把直接赋值吞掉，判定结果会被"继续"按钮挡住。

## 数值口径

- 时间线：楔子 16 岁 → 抵达太衍宗 19 岁。大比限「年不过二十」，失败分支会绕到 19 岁半，**刻意贴着红线**，别再往后加月数了。
- 心境 100 封顶，跌破 30 突破必失败，跌破 20 触发走火入魔（第三章起启用）。
- `simulate.js` 会打印终局境界分布和心境区间，加完剧情看一眼有没有跑飞。
