// draw.js —— ShowCalendar 画图逻辑的 JS 版
// 依赖: @napi-rs/canvas
// 对应原插件 main.py 中的 generate_month_calendar() 与 generate_pie_chart()

const fs = require('fs');
const path = require('path');
const {
  createCanvas,
  GlobalFonts,
} = require('@napi-rs/canvas');

const FONT_FAMILY = 'SimHei';
const FONT_CANDIDATES = [
  path.join(__dirname, 'fonts', 'simhei.ttf'),
  path.join(__dirname, '..', 'fonts', 'simhei.ttf'),
  '/System/Library/Fonts/STHeiti Light.ttc',
  '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
  '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
  '/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf',
  'C:\\Windows\\Fonts\\simhei.ttf',
  'C:\\Windows\\Fonts\\msyh.ttc',
];

let fontRegistered = false;
function ensureFont() {
  if (fontRegistered) return;
  for (const fp of FONT_CANDIDATES) {
    try {
      if (fs.existsSync(fp)) {
        GlobalFonts.registerFromPath(fp, FONT_FAMILY);
        fontRegistered = true;
        return;
      }
    } catch (_) {
      // 尝试下一个
    }
  }
  console.warn('[图片服务] 未找到中文字体，图片中的中文可能显示为方框');
  // 全部失败时使用系统默认字体族
  fontRegistered = true;
}

function makeFont(size, weight) {
  ensureFont();
  return `${weight ? weight + ' ' : ''}${size}px ${FONT_FAMILY}`;
}

function cssColor(rgb) {
  return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
}

// 相当于 Pillow 的 textbbox 宽度
function textWidth(ctx, text, font) {
  ctx.font = font;
  return ctx.measureText(text).width;
}

function textHeight(ctx, text, font) {
  ctx.font = font;
  const m = ctx.measureText(text);
  const h = (m.actualBoundingBoxAscent || 0) + (m.actualBoundingBoxDescent || 0);
  return h > 0 ? h : Number(font.split(' ')[0].replace('px', '')) || 16;
}

function fitText(ctx, text, font, maxWidth) {
  const value = String(text || '');
  if (textWidth(ctx, value, font) <= maxWidth) return value;
  let lo = 0;
  let hi = value.length;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (textWidth(ctx, value.slice(0, mid) + '…', font) <= maxWidth) lo = mid;
    else hi = mid - 1;
  }
  return value.slice(0, lo) + '…';
}

// Pillow draw.ellipse 是外接矩形填充椭圆，canvas 等价为完整椭圆
function fillEllipse(ctx, x0, y0, x1, y1, fill) {
  const rx = (x1 - x0) / 2;
  const ry = (y1 - y0) / 2;
  const cx = (x0 + x1) / 2;
  const cy = (y0 + y1) / 2;
  ctx.beginPath();
  ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
  ctx.fillStyle = cssColor(fill);
  ctx.fill();
}

// Pillow draw.pieslice 等价：中心到弧线再到中心的扇形（角度为弧度，顺时针，从3点钟方向开始）
function fillPieslice(ctx, box, startDeg, endDeg, fill) {
  const cx = (box[0] + box[2]) / 2;
  const cy = (box[1] + box[3]) / 2;
  const r = (box[2] - box[0]) / 2;
  const start = (startDeg * Math.PI) / 180;
  const end = (endDeg * Math.PI) / 180;
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.arc(cx, cy, r, start, end, false);
  ctx.closePath();
  ctx.fillStyle = cssColor(fill);
  ctx.fill();
}

function buildMonthGrid(year, month) {
  const first = new Date(year, month - 1, 1);
  const firstWeekday = (first.getDay() + 6) % 7; // 周一=0
  const daysInMonth = new Date(year, month, 0).getDate();
  const weeks = [];
  let currentWeek = new Array(7).fill(0);
  for (let d = 1; d <= daysInMonth; d++) {
    const idx = (firstWeekday + d - 1) % 7;
    currentWeek[idx] = d;
    if (idx === 6) {
      weeks.push(currentWeek);
      currentWeek = new Array(7).fill(0);
    }
  }
  if (currentWeek.some((x) => x !== 0)) weeks.push(currentWeek);
  return weeks;
}

// 对应 generate_month_calendar
function generateMonthCalendar({
  year,
  month,
  dayShows,       // { day: [showName, ...] }
  showColor,      // { showName: [r,g,b] }
  showTimeRange,  // { showName: 'MM.DD-MM.DD' }
  uid,
  outputPath,
  showNameDict,   // { showName: guestName }
}) {
  const cal = buildMonthGrid(year, month);
  const cellSize = 80;
  const leftMargin = 50;
  const rightMargin = 50;
  const contentWidth = 7 * cellSize;
  const width = contentWidth + leftMargin + rightMargin;
  const rows = cal.length;
  const dateHeight = rows * cellSize;
  const topMargin = 140;

  const legendItems = [];
  const seen = new Set();
  for (const shows of Object.values(dayShows)) {
    for (const show of shows) {
      if (!seen.has(show)) {
        seen.add(show);
        legendItems.push([
          show,
          showColor[show],
          showTimeRange[show] || '',
          (showNameDict && showNameDict[show]) || '',
        ]);
      }
    }
  }

  const legendFont = makeFont(16);
  const dummyCtx = createCanvas(1, 1).getContext('2d');
  const fontHeight = textHeight(dummyCtx, '测试', legendFont);
  const legendLineHeight = fontHeight + 15;
  const legendColumns = legendItems.length > 6 ? 2 : 1;
  const legendRows = Math.ceil(legendItems.length / legendColumns);
  const legendContentHeight = legendRows * legendLineHeight;
  const bottomTextHeight = 20;
  const bottomMargin = 120;
  const legendHeight = legendContentHeight + bottomTextHeight + bottomMargin;
  const height = topMargin + dateHeight + legendHeight;

  const canvas = createCanvas(width, height);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = 'white';
  ctx.fillRect(0, 0, width, height);

  const titleFont = makeFont(24);
  const dayFont = makeFont(18);
  const smallFont = makeFont(12);
  const grayColor = [226, 222, 213];

  // 标题
  const title = `${year}年${month}月`;
  const titleWidth = textWidth(ctx, title, titleFont);
  ctx.fillStyle = 'black';
  ctx.font = titleFont;
  ctx.textBaseline = 'top';
  ctx.fillText(title, leftMargin + (contentWidth - titleWidth) / 2, 20);

  // @uid
  const uidLine = `@${uid}`;
  const uidWidth = textWidth(ctx, uidLine, smallFont);
  const uidY = 20 + 40;
  ctx.fillStyle = cssColor(grayColor);
  ctx.font = smallFont;
  ctx.fillText(uidLine, leftMargin + (contentWidth - uidWidth) / 2, uidY);

  // 星期表头
  const weekdays = ['一', '二', '三', '四', '五', '六', '日'];
  const weekdayY = uidY + 40;
  ctx.fillStyle = 'black';
  ctx.font = dayFont;
  for (let i = 0; i < weekdays.length; i++) {
    const x = leftMargin + i * cellSize + cellSize / 2 - 10;
    ctx.fillStyle = i >= 5 ? 'rgb(190,105,105)' : 'black';
    ctx.fillText(weekdays[i], x, weekdayY);
  }

  const startY = weekdayY + 30;
  // 日期格
  for (let r = 0; r < cal.length; r++) {
    const week = cal[r];
    for (let c = 0; c < 7; c++) {
      const day = week[c];
      if (day === 0) continue;
      const x0 = leftMargin + c * cellSize;
      const y0 = startY + r * cellSize;
      const cx = x0 + cellSize / 2;
      const cy = y0 + cellSize / 2;
      const radius = 30;
      if (dayShows[day] && dayShows[day].length > 0) {
        const shows = dayShows[day];
        const num = shows.length;
        const box = [cx - radius, cy - radius, cx + radius, cy + radius];
        if (num === 1) {
          fillEllipse(ctx, box[0], box[1], box[2], box[3], showColor[shows[0]]);
        } else {
          const anglePer = 360 / num;
          let startAngle = 0;
          for (let i = 0; i < num; i++) {
            const endAngle = startAngle + anglePer;
            fillPieslice(ctx, box, startAngle - 90, endAngle - 90, showColor[shows[i]]);
            startAngle = endAngle;
          }
        }
        if (num > 1) {
          ctx.beginPath();
          ctx.arc(cx, cy, radius + 3, 0, Math.PI * 2);
          ctx.strokeStyle = num >= 3 ? 'rgb(205,92,92)' : 'rgb(220,153,92)';
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      }
      const dayStr = String(day);
      ctx.font = dayFont;
      const dayWidth = textWidth(ctx, dayStr, dayFont);
      ctx.fillStyle = 'black';
      ctx.textBaseline = 'middle';
      ctx.fillText(dayStr, cx - dayWidth / 2, cy);
      if (dayShows[day] && dayShows[day].length > 3) {
        const overlapText = `×${dayShows[day].length}`;
        ctx.font = smallFont;
        ctx.fillStyle = 'rgb(150,70,70)';
        const overlapW = textWidth(ctx, overlapText, smallFont);
        ctx.fillText(overlapText, cx - overlapW / 2, cy + 17);
      }
      const today = new Date();
      if (today.getFullYear() === year && today.getMonth() + 1 === month && today.getDate() === day) {
        ctx.beginPath();
        ctx.arc(cx, cy, radius + 7, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgb(75,135,105)';
        ctx.lineWidth = 2;
        ctx.stroke();
      }
      ctx.textBaseline = 'top';
    }
  }

  // 图例
  const legendTop = startY + dateHeight + 20;
  const circleRadius = 8;
  const columnWidth = contentWidth / legendColumns;
  const offset = 12;
  ctx.font = legendFont;
  for (let i = 0; i < legendItems.length; i++) {
    const [showName, color, timeRange, guestName] = legendItems[i];
    const column = Math.floor(i / legendRows);
    const row = i % legendRows;
    const columnX = leftMargin + column * columnWidth;
    const legendY = legendTop + row * legendLineHeight;
    fillEllipse(
      ctx,
      columnX + offset,
      legendY - circleRadius,
      columnX + offset + 2 * circleRadius,
      legendY + circleRadius,
      color
    );
    const textX = columnX + offset + 2 * circleRadius + 12;
    const legendText = guestName
      ? `${timeRange} ${showName}｜${guestName}`
      : `${timeRange} ${showName}`;
    ctx.fillStyle = 'black';
    ctx.textBaseline = 'middle';
    ctx.fillText(fitText(ctx, legendText, legendFont, columnWidth - (textX - columnX) - 8), textX, legendY);
    ctx.textBaseline = 'top';
  }

  // 底部
  const bottomText = '「技术支持」探丸借客@临皋闲人';
  const bottomWidth = textWidth(ctx, bottomText, smallFont);
  const bottomY = height - bottomTextHeight - 10;
  ctx.fillStyle = cssColor(grayColor);
  ctx.font = smallFont;
  ctx.fillText(bottomText, (width - bottomWidth) / 2, bottomY);

  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, canvas.toBuffer('image/png'));
}

// 保留对外导出的 PALETTE，避免共用该渲染模块的旧代码失效。
const PALETTE = [
  [248, 229, 194], [248, 195, 178], [210, 241, 220],
  [224, 199, 227], [188, 241, 224], [186, 219, 233],
  [255, 229, 124], [222, 235, 181], [225, 249, 255],
];

const OUTCOME_COLORS = {
  HE: [137, 201, 151],
  BE: [215, 143, 137],
  OE: [132, 174, 216],
  '开放式': [184, 154, 207],
  '未填写': [199, 197, 190],
};

// 对应 generate_pie_chart
function generatePieChart({ year, stats, uid, outputPath }) {
  const categories = ['HE', 'BE', 'OE', '开放式', '未填写'];
  const filtered = categories
    .map((cat) => [cat, stats[cat] || 0])
    .filter(([, v]) => v > 0);
  if (filtered.length === 0) return;
  const validCats = filtered.map(([c]) => c);
  const validValues = filtered.map(([, v]) => v);
  const total = validValues.reduce((a, b) => a + b, 0);
  const validColors = validCats.map((cat) => OUTCOME_COLORS[cat]);

  const leftMargin = 60;
  const rightMargin = 60;
  const contentWidth = 400;
  const width = contentWidth + leftMargin + rightMargin; // 520
  const pieRadius = 150;
  const holeRadius = 90;
  const gapDeg = 0.8;
  const titleY = 20;
  const uidY = 60;
  const pieTop = 108;
  const pieCx = width / 2;
  const pieCy = pieTop + pieRadius;
  const legendRowH = 36;
  const swatchSize = 14;
  const legendTop = pieCy + pieRadius + 40;
  const legendHeight = validCats.length * legendRowH;
  const bottomTextHeight = 20;
  const bottomMargin = 10;
  const techMarginTop = 120;
  const height =
    legendTop + legendHeight + techMarginTop + bottomTextHeight + bottomMargin;

  const bgColor = [255, 255, 255];
  const canvas = createCanvas(width, height);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = cssColor(bgColor);
  ctx.fillRect(0, 0, width, height);

  const fontTitle = makeFont(24);
  const fontUid = makeFont(12);
  const fontLegend = makeFont(16);
  const fontPct = makeFont(13);
  const fontBottom = makeFont(12);
  const cPrimary = [30, 30, 30];
  const cTertiary = [175, 173, 165];
  const grayColor = [226, 222, 213];

  function drawCentered(text, y, font, fill) {
    const w = textWidth(ctx, text, font);
    ctx.font = font;
    ctx.fillStyle = cssColor(fill);
    ctx.textBaseline = 'top';
    ctx.fillText(text, (width - w) / 2, y);
  }

  drawCentered(`${year}年结局统计`, titleY, fontTitle, cPrimary);
  const uidLine = `@${uid}`;
  const uidWidth = textWidth(ctx, uidLine, fontUid);
  ctx.font = fontUid;
  ctx.fillStyle = cssColor(grayColor);
  ctx.fillText(uidLine, (width - uidWidth) / 2, uidY);

  // 甜甜圈扇区
  const outerBox = [
    pieCx - pieRadius,
    pieCy - pieRadius,
    pieCx + pieRadius,
    pieCy + pieRadius,
  ];
  let cursor = -90.0;
  for (let i = 0; i < validValues.length; i++) {
    const v = validValues[i];
    const color = validColors[i];
    const raw = (v / total) * 360;
    const start = cursor + gapDeg / 2;
    const end = cursor + raw - gapDeg / 2;
    if (end > start) {
      fillPieslice(ctx, outerBox, start, end, color);
    }
    cursor += raw;
  }
  // 中心挖洞
  ctx.beginPath();
  ctx.arc(pieCx, pieCy, holeRadius, 0, Math.PI * 2);
  ctx.fillStyle = cssColor(bgColor);
  ctx.fill();

  // 圆环中心直接展示样本总数。
  drawCentered(String(total), pieCy - 24, makeFont(30, 'bold'), cPrimary);
  drawCentered('总场数', pieCy + 14, fontPct, cTertiary);

  // 计算数量+百分比组合宽度以右对齐
  let maxComboWidth = 0;
  const comboInfo = [];
  for (const count of validValues) {
    const countStr = String(count);
    const pctStr = `${Math.round((count / total) * 100)}%`;
    const countW = textWidth(ctx, countStr, fontLegend);
    const pctW = textWidth(ctx, pctStr, fontPct);
    const spacing = 15;
    const comboW = countW + spacing + pctW;
    if (comboW > maxComboWidth) maxComboWidth = comboW;
    comboInfo.push([countStr, pctStr, countW, pctW]);
  }

  // 图例
  for (let i = 0; i < validCats.length; i++) {
    const cat = validCats[i];
    const color = validColors[i];
    const [countStr, pctStr, countW, pctW] = comboInfo[i];
    const rowY = legendTop + i * legendRowH;
    const cyRow = rowY + legendRowH / 2;
    const r = swatchSize / 2;
    fillEllipse(
      ctx,
      leftMargin - r,
      cyRow - r,
      leftMargin + r,
      cyRow + r,
      color
    );
    const catX = leftMargin + swatchSize + 12;
    ctx.font = fontLegend;
    ctx.fillStyle = cssColor(cPrimary);
    ctx.textBaseline = 'middle';
    ctx.fillText(cat, catX, cyRow);

    const comboX = width - rightMargin - maxComboWidth;
    const countX = comboX;
    ctx.font = fontLegend;
    ctx.fillText(countStr, countX, cyRow);
    const pctX = comboX + maxComboWidth - pctW;
    ctx.font = fontPct;
    ctx.fillStyle = cssColor(cTertiary);
    ctx.fillText(pctStr, pctX, cyRow);
    ctx.textBaseline = 'top';
  }

  const bottomText = '「技术支持」探丸借客@临皋闲人';
  const bottomWidth = textWidth(ctx, bottomText, fontBottom);
  const bottomY = height - bottomTextHeight - 10;
  ctx.font = fontBottom;
  ctx.fillStyle = cssColor(grayColor);
  ctx.textBaseline = 'top';
  ctx.fillText(bottomText, (width - bottomWidth) / 2, bottomY);

  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, canvas.toBuffer('image/png'));
}

// 12 个月的年度档期热力总览。
function generateYearOverview({ year, months, summary, uid, outputPath }) {
  const width = 760;
  const left = 46;
  const top = 112;
  const monthW = 222;
  const monthH = 160;
  const gapX = 18;
  const gapY = 18;
  const cell = 27;
  const height = top + 4 * monthH + 3 * gapY + 130;
  const canvas = createCanvas(width, height);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = 'white';
  ctx.fillRect(0, 0, width, height);
  ctx.textBaseline = 'top';

  const titleFont = makeFont(26, 'bold');
  const monthFont = makeFont(17, 'bold');
  const weekdayFont = makeFont(11);
  const dayFont = makeFont(11);
  const smallFont = makeFont(12);
  const primary = [35, 35, 35];
  const muted = [155, 151, 143];
  const heatColors = {
    1: [215, 236, 222],
    2: [249, 215, 158],
    3: [232, 157, 145],
  };

  ctx.font = titleFont;
  ctx.fillStyle = cssColor(primary);
  const title = `${year}年档期总览`;
  ctx.fillText(title, (width - textWidth(ctx, title, titleFont)) / 2, 20);
  ctx.font = smallFont;
  ctx.fillStyle = cssColor(muted);
  const uidText = `@${uid}`;
  ctx.fillText(uidText, (width - textWidth(ctx, uidText, smallFont)) / 2, 59);

  const weekdays = ['一', '二', '三', '四', '五', '六', '日'];
  for (let month = 1; month <= 12; month++) {
    const col = (month - 1) % 3;
    const row = Math.floor((month - 1) / 3);
    const x0 = left + col * (monthW + gapX);
    const y0 = top + row * (monthH + gapY);
    const monthData = (months || []).find(item => Number(item.month) === month) || { dayCounts: {} };
    const grid = buildMonthGrid(year, month);

    ctx.font = monthFont;
    ctx.fillStyle = cssColor(primary);
    ctx.fillText(`${month}月`, x0, y0);
    for (let c = 0; c < 7; c++) {
      ctx.font = weekdayFont;
      ctx.fillStyle = c >= 5 ? 'rgb(190,105,105)' : cssColor(muted);
      ctx.fillText(weekdays[c], x0 + c * cell + 8, y0 + 27);
    }

    for (let r = 0; r < grid.length; r++) {
      for (let c = 0; c < 7; c++) {
        const day = grid[r][c];
        if (!day) continue;
        const x = x0 + c * cell;
        const y = y0 + 48 + r * 18;
        const count = Number(monthData.dayCounts && monthData.dayCounts[day]) || 0;
        if (count > 0) {
          ctx.fillStyle = cssColor(heatColors[Math.min(3, count)]);
          ctx.beginPath();
          ctx.roundRect(x + 2, y - 2, 23, 17, 4);
          ctx.fill();
        }
        ctx.font = dayFont;
        ctx.fillStyle = count >= 3 ? 'rgb(115,45,45)' : cssColor(primary);
        const dayText = String(day);
        ctx.fillText(dayText, x + (27 - textWidth(ctx, dayText, dayFont)) / 2, y);
      }
    }
  }

  const summaryY = top + 4 * monthH + 3 * gapY + 24;
  const totalShows = Number(summary && summary.totalShows) || 0;
  const occupiedDays = Number(summary && summary.occupiedDays) || 0;
  const conflictDays = Number(summary && summary.conflictDays) || 0;
  const busiestMonth = Number(summary && summary.busiestMonth) || 0;
  const summaryText = `共 ${totalShows} 场  ·  在档 ${occupiedDays} 天  ·  重叠 ${conflictDays} 天` +
    (busiestMonth ? `  ·  最忙 ${busiestMonth}月` : '');
  ctx.font = makeFont(16);
  ctx.fillStyle = cssColor(primary);
  ctx.fillText(summaryText, (width - textWidth(ctx, summaryText, ctx.font)) / 2, summaryY);

  const legendY = summaryY + 43;
  const labels = [['1场', heatColors[1]], ['2场', heatColors[2]], ['3场及以上', heatColors[3]]];
  let legendX = 244;
  for (const [label, color] of labels) {
    ctx.fillStyle = cssColor(color);
    ctx.fillRect(legendX, legendY, 14, 14);
    ctx.font = smallFont;
    ctx.fillStyle = cssColor(muted);
    ctx.fillText(label, legendX + 20, legendY - 1);
    legendX += label === '3场及以上' ? 0 : 90;
  }

  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, canvas.toBuffer('image/png'));
}

// ==================== 战棋棋盘渲染 ====================

const TEAM_COLORS = {
  blue: [104, 132, 186],   // 蓝方（我方）
  red: [205, 130, 120],    // 红方（PVP对手）
  boss: [170, 110, 150],   // Boss
};

// 对应战棋棋盘图片
function generateBoard({
  grid,          // 6x6 数组，每格为单位名或 ''
  units,         // { name: { team, alive, hp, maxHp, atk, def, mov, rng, pos, skills } }
  players,       // [name, ...]
  bosses,        // { bossName: cfg }
  mode,          // 'PVE' | 'PVP'
  round,         // 当前回合
  currentPlayer, // 当前行动玩家名
  uid,
  outputPath,
}) {
  const ROWS = 6;
  const COLS = 6;
  const cellSize = 96;
  const leftMargin = 56;
  const rightMargin = 56;
  const contentWidth = COLS * cellSize;
  const width = contentWidth + leftMargin + rightMargin;
  const topMargin = 150;
  const boardTop = topMargin;
  const boardH = ROWS * cellSize;

  const bossKeys = Object.keys(bosses || {});
  const unitTag = (name, u) => {
    if ( u.team === 0 ) return 'B' + (players.indexOf(name) + 1);
    if ( u.team === 1 ) return 'R' + (players.indexOf(name) + 1);
    return 'X' + (bossKeys.indexOf(name) + 1);
  };
  const unitColor = (u) => {
    if ( u.team === 1 ) return TEAM_COLORS.red;
    if ( u.team === -1 ) return TEAM_COLORS.boss;
    return TEAM_COLORS.blue;
  };

  // 图例条目
  const legendItems = [];
  const appendLegend = (name, u) => {
    if ( !u ) return;
    legendItems.push({
      tag: unitTag(name, u),
      name: name,
      color: unitColor(u),
      hp: u.hp,
      maxHp: u.maxHp,
      atk: u.atk,
      def: u.def || 0,
      mov: u.mov,
      rng: u.rng,
      skills: u.skills || [],
      alive: !!u.alive,
    });
  };
  for ( const p of players ) appendLegend(p, units[p]);
  for ( const bn of bossKeys ) appendLegend(bn, units[bn]);

  const legendLineH = 36;
  const legendH = legendItems.length * legendLineH + 24;
  const bottomTextHeight = 24;
  const height = boardTop + boardH + 24 + legendH + bottomTextHeight + 12;

  const canvas = createCanvas(width, height);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, width, height);

  const fontTitle = makeFont(24);
  const fontSmall = makeFont(12);
  const fontCell = makeFont(13);
  const fontTag = makeFont(22, 'bold');
  const fontHp = makeFont(12);
  const fontLegend = makeFont(16);

  const cPrimary = [40, 40, 40];
  const cTertiary = [150, 148, 140];
  const grayColor = [226, 222, 213];
  const cellA = [250, 248, 243];
  const cellB = [241, 238, 231];
  const gridColor = [224, 220, 212];

  // 标题
  const modeLabel = mode === 'PVE' ? 'PVE' : 'PVP';
  const title = `战棋 ${modeLabel}` + (round ? `  第 ${round} 回合` : '');
  const titleW = textWidth(ctx, title, fontTitle);
  ctx.font = fontTitle;
  ctx.fillStyle = cssColor(cPrimary);
  ctx.textBaseline = 'top';
  ctx.fillText(title, (width - titleW) / 2, 18);

  // uid
  const uidLine = `@${uid}`;
  const uidW = textWidth(ctx, uidLine, fontSmall);
  ctx.font = fontSmall;
  ctx.fillStyle = cssColor(grayColor);
  ctx.fillText(uidLine, (width - uidW) / 2, 54);

  // 行动提示
  const turnLine = currentPlayer ? `当前行动：${currentPlayer}` : '等待开始';
  const turnW = textWidth(ctx, turnLine, fontSmall);
  ctx.font = fontSmall;
  ctx.fillStyle = cssColor(cTertiary);
  ctx.fillText(turnLine, (width - turnW) / 2, 74);

  // 列坐标
  ctx.font = fontCell;
  ctx.fillStyle = cssColor(cTertiary);
  ctx.textBaseline = 'middle';
  for ( let c = 0; c < COLS; c++ ) {
    const cx = leftMargin + c * cellSize + cellSize / 2;
    ctx.fillText(String(c), cx, 126);
  }

  // 画格子
  for ( let r = 0; r < ROWS; r++ ) {
    // 行坐标
    ctx.font = fontCell;
    ctx.fillStyle = cssColor(cTertiary);
    ctx.textBaseline = 'middle';
    ctx.fillText(String(r), 22, boardTop + r * cellSize + cellSize / 2);

    for ( let c = 0; c < COLS; c++ ) {
      const x0 = leftMargin + c * cellSize;
      const y0 = boardTop + r * cellSize;
      ctx.fillStyle = cssColor((r + c) % 2 === 0 ? cellA : cellB);
      ctx.fillRect(x0, y0, cellSize, cellSize);
      ctx.strokeStyle = cssColor(gridColor);
      ctx.lineWidth = 1;
      ctx.strokeRect(x0 + 0.5, y0 + 0.5, cellSize - 1, cellSize - 1);

      const name = grid && grid[r] && grid[r][c];
      const u = name ? units[name] : null;
      if ( !name || !u || !u.alive ) continue;

      // 当前行动单位高亮
      if ( currentPlayer && name === currentPlayer ) {
        ctx.strokeStyle = cssColor([232, 170, 70]);
        ctx.lineWidth = 3;
        ctx.strokeRect(x0 + 1.5, y0 + 1.5, cellSize - 3, cellSize - 3);
        ctx.lineWidth = 1;
      }

      const cx = x0 + cellSize / 2;
      const cy = y0 + cellSize / 2;
      const radius = 32;
      fillEllipse(ctx, cx - radius, cy - radius, cx + radius, cy + radius, unitColor(u));

      // 标签
      const tag = unitTag(name, u);
      ctx.font = fontTag;
      ctx.fillStyle = '#ffffff';
      ctx.textBaseline = 'middle';
      const tagW = textWidth(ctx, tag, fontTag);
      ctx.fillText(tag, cx - tagW / 2, cy - 10);

      // HP 数值
      const hpStr = `${u.hp}/${u.maxHp}`;
      ctx.font = fontHp;
      const hpW = textWidth(ctx, hpStr, fontHp);
      ctx.fillText(hpStr, cx - hpW / 2, cy + 12);
      ctx.textBaseline = 'top';

      // HP 条
      const barW = cellSize - 20;
      const barH = 6;
      const barX = x0 + 10;
      const barY = y0 + cellSize - 14;
      const pct = Math.max(0, Math.min(1, u.hp / (u.maxHp || 1)));
      ctx.fillStyle = cssColor([80, 80, 85]);
      ctx.fillRect(barX, barY, barW, barH);
      ctx.fillStyle = cssColor(pct > 0.5 ? [102, 187, 120] : pct > 0.25 ? [230, 188, 82] : [224, 96, 96]);
      ctx.fillRect(barX, barY, Math.max(2, barW * pct), barH);
    }
  }

  // 图例
  let legendY = boardTop + boardH + 24;
  ctx.font = fontLegend;
  ctx.textBaseline = 'middle';
  for ( const item of legendItems ) {
    const r = 9;
    fillEllipse(ctx, leftMargin - r, legendY - r, leftMargin + r, legendY + r, item.color);
    ctx.fillStyle = cssColor(cPrimary);
    const legendText =
      `${item.tag} ${item.name}  生命 ${item.hp}/${item.maxHp}  攻击 ${item.atk}  防御 ${item.def}  移动 ${item.mov}  范围 ${item.rng}` +
      (item.skills.length > 0 ? `  技能 ${item.skills.join('、')}` : '') +
      (item.alive ? '' : '  （已阵亡）');
    ctx.fillText(legendText, leftMargin + 2 * r + 14, legendY);
    legendY += legendLineH;
  }
  ctx.textBaseline = 'top';

  // 底部
  const bottomText = '@为人苹命';
  const bottomW = textWidth(ctx, bottomText, fontSmall);
  const bottomY = height - bottomTextHeight - 10;
  ctx.font = fontSmall;
  ctx.fillStyle = cssColor(grayColor);
  ctx.fillText(bottomText, (width - bottomW) / 2, bottomY);

  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, canvas.toBuffer('image/png'));
}

module.exports = {
  generateMonthCalendar,
  generatePieChart,
  generateYearOverview,
  generateBoard,
  buildMonthGrid,
  PALETTE,
};
