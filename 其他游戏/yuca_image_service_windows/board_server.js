// board_server.js —— 图片渲染 HTTP 服务（战棋棋盘 + 语擦助手日历/结局图）
// 依赖: draw.js (@napi-rs/canvas)
// 启动: node board_server.js  （默认端口 8855，可用环境变量 BOARD_SERVER_PORT 修改）
// 接口:
//   GET  /ping       健康检查
//   GET  /output/<filename>  取回一次生成的 PNG（60 秒后自动清理，见下方说明）
//   POST /board      战棋棋盘状态 JSON，返回 { ok, base64, filename, url }
//   POST /calendar   语擦助手月历状态 JSON，返回 { ok, base64, filename, url }
//   POST /pie        语擦助手结局分布 JSON，返回 { ok, base64, filename, url }
//   POST /year-overview 语擦助手年度热力图 JSON，返回 { ok, base64, filename, url }
//
// url 字段是给海豹插件用的：不同 QQ 协议端（NapCat/LLOneBot/Lagrange...）对
// CQ 码里 file=base64://（太长会被海豹自身的分段逻辑拆碎）和 file=file://
// 本地路径（部分协议端出于安全考虑直接拒绝，报"资源路径受限"）的支持不一致，
// 只有 file=http://... 网址这种引用方式是所有协议端都通用支持的，所以现在
// 生成的图片会保留一小段时间、通过这个 HTTP 接口对外提供，而不是马上删除。
// base64 字段仍然保留，是给「恋综：战棋」那边现有代码（直接用 base64://）
// 兼容用的，不建议新代码再依赖它。

const http = require('http');
const path = require('path');
const fs = require('fs');
const { generateBoard, generateMonthCalendar, generatePieChart, generateYearOverview } = require('./draw.js');

const PORT = process.env.BOARD_SERVER_PORT || 8855;
const MAX_BODY_BYTES = 2 * 1024 * 1024;
const OUTPUT_DIR = path.join(__dirname, 'output');
fs.mkdirSync(OUTPUT_DIR, { recursive: true });

const sendJson = (res, code, obj) => {
  res.writeHead(code, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(obj));
};

// PNG 文件名格式，同时用于：清理历史文件 + /output 路由的合法性校验（防止
// 用这个接口读到 output 目录之外的任意文件）
const IMAGE_FILENAME_RE = /^(board|calendar|pie|year-overview)_\d+_\d+\.png$/;

// 清理历史图片（进程重启时残留的旧文件，正常运行时靠下面的 60 秒定时器清理）
const cleanupOldImages = () => {
  try {
    const files = fs.readdirSync(OUTPUT_DIR).filter((f) => IMAGE_FILENAME_RE.test(f));
    files.forEach((f) => fs.unlinkSync(path.join(OUTPUT_DIR, f)));
    if (files.length > 0) console.log(`[image service] Cleaned up ${files.length} stale image(s)`);
  } catch (e) { /* 忽略 */ }
};
cleanupOldImages();

// 每张生成的图片保留这么久，供协议端通过 /output/<filename> 取回，之后自动删除
const OUTPUT_RETENTION_MS = 60 * 1000;

// 三个渲染接口共用的处理逻辑：解析请求体 -> 生成 PNG -> 转 base64 -> 响应
// （PNG 文件本身不再立即删除，改成 OUTPUT_RETENTION_MS 后自动清理，见下方 /output 路由）
const handleRenderRequest = (req, res, prefix, generateFn) => {
  let body = '';
  let bodyBytes = 0;
  let rejected = false;
  req.on('data', (chunk) => {
    if (rejected) return;
    bodyBytes += chunk.length;
    if (bodyBytes > MAX_BODY_BYTES) {
      rejected = true;
      sendJson(res, 413, { ok: false, error: '请求数据超过 2MB 限制' });
      return;
    }
    body += chunk;
  });
  req.on('end', () => {
    if (rejected) return;
    let outputPath = '';
    try {
      const data = JSON.parse(body);
      if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('请求数据必须是 JSON 对象');
      if (prefix === 'calendar') {
        if (!Number.isInteger(data.year) || data.year < 1900 || data.year > 2100) throw new Error('无效的年份');
        if (!Number.isInteger(data.month) || data.month < 1 || data.month > 12) throw new Error('无效的月份');
        if (!data.dayShows || typeof data.dayShows !== 'object') throw new Error('缺少日历数据');
      }
      if (prefix === 'pie' && (!data.stats || typeof data.stats !== 'object')) throw new Error('缺少统计数据');
      if (prefix === 'year-overview') {
        if (!Number.isInteger(data.year) || data.year < 1900 || data.year > 2100) throw new Error('无效的年份');
        if (!Array.isArray(data.months) || data.months.length !== 12) throw new Error('年度总览需要 12 个月的数据');
      }
      const filename = `${prefix}_${Date.now()}_${Math.floor(Math.random() * 10000)}.png`;
      outputPath = path.join(OUTPUT_DIR, filename);
      generateFn(Object.assign({}, data, { outputPath }));
      const base64 = fs.readFileSync(outputPath).toString('base64');
      const url = `http://127.0.0.1:${PORT}/output/${filename}`;
      // 生成失败/响应失败时立即清理；成功时保留 OUTPUT_RETENTION_MS 供协议端取回。
      outputPath = '';
      setTimeout(() => {
        try { fs.unlinkSync(path.join(OUTPUT_DIR, filename)); } catch (e) { /* 忽略，可能已经被清理过 */ }
      }, OUTPUT_RETENTION_MS);
      return sendJson(res, 200, { ok: true, base64, filename, url });
    } catch (e) {
      console.error(`[image service] /${prefix} generation failed:`, e && e.message || e);
      return sendJson(res, 500, { ok: false, error: String(e && e.message || e) });
    } finally {
      // 只有渲染/读取过程本身出错时才会走到这里（outputPath 在成功路径上已被清空），
      // 尽力删除半成品 PNG。
      if (outputPath) {
        try { if (fs.existsSync(outputPath)) fs.unlinkSync(outputPath); } catch (e) { /* 忽略 */ }
      }
    }
  });
};

const server = http.createServer((req, res) => {
  if ( req.method === 'GET' && req.url === '/ping' ) {
    return sendJson(res, 200, { ok: true });
  }
  if ( req.method === 'GET' && req.url.startsWith('/output/') ) {
    const filename = req.url.slice('/output/'.length);
    if (!IMAGE_FILENAME_RE.test(filename)) {
      return sendJson(res, 404, { ok: false, error: 'not found' });
    }
    const filePath = path.join(OUTPUT_DIR, filename);
    return fs.readFile(filePath, (err, data) => {
      if (err) return sendJson(res, 404, { ok: false, error: 'not found or already expired' });
      res.writeHead(200, { 'Content-Type': 'image/png', 'Content-Length': data.length });
      res.end(data);
    });
  }
  if ( req.method === 'POST' && req.url === '/board' ) {
    return handleRenderRequest(req, res, 'board', generateBoard);
  }
  if ( req.method === 'POST' && req.url === '/calendar' ) {
    return handleRenderRequest(req, res, 'calendar', generateMonthCalendar);
  }
  if ( req.method === 'POST' && req.url === '/pie' ) {
    return handleRenderRequest(req, res, 'pie', generatePieChart);
  }
  if ( req.method === 'POST' && req.url === '/year-overview' ) {
    return handleRenderRequest(req, res, 'year-overview', generateYearOverview);
  }
  return sendJson(res, 404, { ok: false, error: 'not found' });
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`[image service] Started: http://127.0.0.1:${PORT} - /board /calendar /pie /year-overview /output`);
  console.log(`[image service] Keep this window open; closing it stops the service.`);
});

server.on('error', (e) => {
  console.error(`[image service] Startup failed: ${e && e.message || e}`);
  console.error(`[image service] Common causes: port ${PORT} already in use, or insufficient permissions.`);
  console.error(`[image service] To change port: set BOARD_SERVER_PORT=9000 then restart.`);
  process.exit(1);
});

process.on('uncaughtException', (e) => {
  console.error('[image service] Exception:', e && e.stack || e);
});
