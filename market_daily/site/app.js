(function () {
  'use strict';

  var app = document.getElementById('app');
  var dlg = document.getElementById('archive');
  var listEl = document.getElementById('archive-list');
  var ED = { am: '早报', pm: '晚报' };
  var ED_TIME = { am: '纽约时间 8:30 版', pm: '纽约时间 17:00 版' };
  var index = [];

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function safeUrl(u) { return /^https?:\/\//i.test(u || '') ? u : ''; }

  // 红涨绿跌（A 股习惯）
  function tone(v) {
    var s = String(v == null ? '' : v).trim();
    if (/^[+＋]/.test(s)) return 'up';
    if (/^[-−–—]/.test(s)) return 'down';
    return 'flat';
  }
  function dirTone(d) {
    d = String(d || '');
    if (/利好|看多|偏多|正面/.test(d)) return 'pos';
    if (/利空|看空|偏空|负面/.test(d)) return 'neg';
    return 'mid';
  }

  function fmtDate(date) {
    var d = new Date(date + 'T12:00:00Z');
    return new Intl.DateTimeFormat('zh-CN', {
      timeZone: 'UTC', year: 'numeric', month: 'long', day: 'numeric', weekday: 'long'
    }).format(d);
  }
  function fmtShort(date) {
    var p = date.split('-');
    return Number(p[1]) + '月' + Number(p[2]) + '日';
  }
  function fmtStamp(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    if (isNaN(d)) return '';
    return new Intl.DateTimeFormat('zh-CN', {
      timeZone: 'America/New_York', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false
    }).format(d) + ' 纽约时间';
  }

  function paras(arr) {
    return (arr || []).map(function (p) { return '<p>' + esc(p) + '</p>'; }).join('');
  }

  function pageHead(title, sub) {
    return '<header class="page-head"><h2>' + esc(title) + '</h2>' +
      (sub ? '<span class="sub">' + esc(sub) + '</span>' : '') + '</header>';
  }

  function chgCell(v) {
    return '<td class="r num ' + tone(v) + '">' + esc(v) + '</td>';
  }

  function tape(items, note) {
    if (!items || !items.length) return '';
    return '<section class="tape" aria-label="行情">' + items.map(function (q) {
      return '<div class="q"><b>' + esc(q.name) + '</b><span class="v num">' + esc(q.value) +
        '</span><span class="c num ' + tone(q.chg) + '">' + esc(q.chg) + '</span></div>';
    }).join('') + '</section><p class="legend">红涨绿跌。' + esc(note || '行情为该版截稿时数据，收盘价以交易所为准。') + '</p>';
  }

  function secMarkets(s) {
    if (!s) return '';
    var h = pageHead(s.title || '市场论述', s.sub);
    var out = '<section class="page" id="markets">' + h;
    if (s.lede) out += '<p class="lede">' + esc(s.lede) + '</p>';
    out += '<div class="prose">' + paras(s.body) + '</div>';
    var blocks = '';
    if (s.catalysts && s.catalysts.length) {
      blocks += '<div class="block"><h3>新闻催化</h3><ul class="cat">' + s.catalysts.map(function (c) {
        return '<li><span class="w">' + esc([c.when, c.where].filter(Boolean).join(' ')) + '</span><span>' + esc(c.text) + '</span></li>';
      }).join('') + '</ul></div>';
    }
    if (s.sectors && s.sectors.length) {
      blocks += '<div class="block"><h3>美股板块</h3><table><thead><tr><th>板块</th><th class="r">涨跌</th><th>原因</th></tr></thead><tbody>' +
        s.sectors.map(function (r) {
          return '<tr><td class="n">' + esc(r.name) + '</td>' + chgCell(r.chg) + '<td>' + esc(r.reason) + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    if (s.global && s.global.length) {
      blocks += '<div class="block wide"><h3>全球市场</h3><table><thead><tr><th>市场</th><th class="r">涨跌</th><th>说明</th></tr></thead><tbody>' +
        s.global.map(function (r) {
          return '<tr><td class="n">' + esc(r.name) + '</td>' + chgCell(r.chg) + '<td>' + esc(r.note) + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    if (blocks) out += '<div class="grids">' + blocks + '</div>';
    return out + '</section>';
  }

  function idxStrip(ix) {
    if (!ix) return '';
    var cells = '<div class="q main"><b>' + esc(ix.name) + '</b><span class="v num">' + esc(ix.value) +
      '</span><span class="c num ' + tone(ix.chg) + '">' + esc(ix.chg) + '</span></div>';
    if (ix.week) cells += '<div class="q"><b>一周</b><span class="v num ' + tone(ix.week) + '">' + esc(ix.week) + '</span></div>';
    (ix.days || []).forEach(function (d) {
      cells += '<div class="q"><b>' + esc(d.d) + '</b><span class="v num ' + tone(d.chg) + '">' + esc(d.chg) + '</span></div>';
    });
    return '<section class="tape idx" aria-label="' + esc(ix.name) + '">' + cells + '</section>' +
      (ix.note ? '<p class="legend">' + esc(ix.note) + '</p>' : '') + '<div class="idx-gap"></div>';
  }

  function secAi(s) {
    if (!s) return '';
    var out = '<section class="page" id="ai">' + pageHead(s.title || 'AI 板块与费城半导体指数', s.sub);
    if (s.lede) out += '<p class="lede">' + esc(s.lede) + '</p>';
    out += idxStrip(s.index);
    out += '<div class="prose">' + paras(s.body) + '</div>';
    if (s.stocks && s.stocks.length) {
      out += '<div class="grids"><div class="block wide"><h3>个股</h3><table><thead><tr><th>代码</th><th>名称</th><th class="r">收盘/最新</th><th class="r">涨跌</th><th>一句话</th></tr></thead><tbody>' +
        s.stocks.map(function (r) {
          return '<tr><td class="n num">' + esc(r.symbol) + '</td><td>' + esc(r.name) + '</td><td class="r num">' + esc(r.price) + '</td>' +
            chgCell(r.chg) + '<td>' + esc(r.note) + '</td></tr>';
        }).join('') + '</tbody></table></div></div>';
    }
    return out + '</section>';
  }

  function dirTag(d) { return '<span class="dir ' + dirTone(d) + '">' + esc(d) + '</span>'; }

  function secChina(s) {
    if (!s) return '';
    var out = '<section class="page" id="china">' + pageHead(s.title || '中国 AI 映射', s.sub || '美股信号传导到 A 股与港股');
    if (s.lede) out += '<p class="lede">' + esc(s.lede) + '</p>';
    out += '<div class="prose">' + paras(s.body) + '</div>';
    if (s.mapping && s.mapping.length) {
      out += '<div class="grids"><div class="block wide"><h3>传导链条</h3><table><thead><tr><th>美股端的变化</th><th>对应的中国板块</th><th>代表标的</th><th>方向</th><th>判断</th></tr></thead><tbody>' +
        s.mapping.map(function (r) {
          return '<tr><td>' + esc(r.driver) + '</td><td class="n">' + esc(r.sector) + '</td><td>' + esc(r.names) + '</td><td>' + dirTag(r.dir) + '</td><td>' + esc(r.note) + '</td></tr>';
        }).join('') + '</tbody></table></div></div>';
    }
    return out + '</section>';
  }

  function secPolicy(s) {
    if (!s) return '';
    var out = '<section class="page" id="policy">' + pageHead(s.title || '美联储与政策', s.sub);
    if (s.lede) out += '<p class="lede">' + esc(s.lede) + '</p>';
    out += '<div class="prose">' + paras(s.body) + '</div>';
    var blocks = '';
    if (s.outlook && s.outlook.length) {
      blocks += '<div class="block wide"><h3>前瞻与影响</h3><table><thead><tr><th>事项</th><th>对市场</th><th>时间</th><th>判断</th></tr></thead><tbody>' +
        s.outlook.map(function (r) {
          return '<tr><td class="n">' + esc(r.item) + '</td><td>' + dirTag(r.dir) + '</td><td class="num">' + esc(r.horizon) + '</td><td>' + esc(r.note) + '</td></tr>';
        }).join('') + '</tbody></table></div>';
    }
    if (s.calendar && s.calendar.length) {
      blocks += '<div class="block wide"><h3>接下来要看</h3><ul class="cat">' + s.calendar.map(function (c) {
        return '<li><span class="w num">' + esc(c.when) + '</span><span>' + esc(c.event) + '</span></li>';
      }).join('') + '</ul></div>';
    }
    if (blocks) out += '<div class="grids">' + blocks + '</div>';
    return out + '</section>';
  }


  // ---------- 大事预告 + 倒计时 ----------
  var timer = null;
  function fmtAt(iso, tz) {
    var d = new Date(iso);
    if (isNaN(d)) return '';
    return new Intl.DateTimeFormat('zh-CN', {
      timeZone: tz, month: 'numeric', day: 'numeric', weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false
    }).format(d);
  }
  function fmtDay(iso) {
    var d = new Date(iso);
    if (isNaN(d)) return '';
    return new Intl.DateTimeFormat('zh-CN', {
      timeZone: 'America/New_York', month: 'numeric', day: 'numeric', weekday: 'short'
    }).format(d);
  }
  function pad(n) { return n < 10 ? '0' + n : String(n); }
  function countdown(ms, allDay) {
    if (ms <= 0) return null;
    var t = Math.floor(ms / 1000);
    var d = Math.floor(t / 86400), h = Math.floor(t % 86400 / 3600), m = Math.floor(t % 3600 / 60), sec = t % 60;
    if (allDay) return d + ' 天';
    return (d > 0 ? d + ' 天 ' : '') + pad(h) + ':' + pad(m) + ':' + pad(sec);
  }
  function tick() {
    var nodes = document.querySelectorAll('[data-at]');
    var now = Date.now();
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      var c = countdown(new Date(n.getAttribute('data-at')).getTime() - now, n.getAttribute('data-allday') === '1');
      var card = n.closest('.ev');
      if (c === null) { n.textContent = '已过'; if (card) card.classList.add('past'); }
      else { n.textContent = c; if (card) card.classList.remove('past'); }
    }
  }
  function secUpcoming(list) {
    if (!list || !list.length) return '';
    var evs = list.slice().sort(function (a, b) { return new Date(a.at) - new Date(b.at); });
    var out = '<section class="page upcoming" id="upcoming">' + pageHead('大事预告', '倒计时按你电脑的当前时间走');
    out += '<div class="evs">' + evs.map(function (e) {
      var url = safeUrl(e.src);
      var when = e.all_day
        ? '<span>' + esc(fmtDay(e.at)) + '（美东全天）</span>'
        : '<span>纽约 ' + esc(fmtAt(e.at, 'America/New_York')) + '</span><span>北京 ' + esc(fmtAt(e.at, 'Asia/Shanghai')) + '</span>';
      return '<article class="ev' + (e.importance === 'high' ? ' high' : '') + '">' +
        '<p class="tag"><b>' + esc(e.kind) + '</b>' + (e.importance === 'high' ? '<i>重要</i>' : '') + '</p>' +
        '<h3>' + esc(e.title) + '</h3>' +
        '<p class="cd num" data-at="' + esc(e.at) + '"' + (e.all_day ? ' data-allday="1"' : '') + '></p>' +
        '<p class="when num">' + when + '</p>' +
        (e.note ? '<p class="note">' + esc(e.note) + '</p>' : '') +
        (url ? '<a class="src" href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">依据</a>' : '') +
        '</article>';
    }).join('') + '</div></section>';
    return out;
  }

  function renderIssue(it) {
    var ed = it.edition === 'pm' ? 'pm' : 'am';
    var pos = index.map(function (x) { return x.id; }).indexOf(it.id); // index 为新到旧
    var no = pos >= 0 ? index.length - pos : '';
    var newer = pos > 0 ? index[pos - 1] : null;
    var older = pos >= 0 && pos < index.length - 1 ? index[pos + 1] : null;

    document.body.setAttribute('data-ed', ed);
    document.title = '纽约晨昏 ' + fmtShort(it.date) + ED[ed];

    var html = '';
    html += '<div class="topline"><span>' + (no ? '第 ' + esc(no) + ' 期' : '') + '</span>' +
      '<span class="pager">' +
      '<button id="prev"' + (older ? '' : ' disabled') + '>前一版</button>' +
      '<button id="arc">往期</button>' +
      '<button id="next"' + (newer ? '' : ' disabled') + '>后一版</button></span></div>';

    html += '<header class="masthead"><h1>纽约晨昏</h1><p class="edline">' +
      '<span class="ed">' + ED[ed] + '</span><span>' + esc(fmtDate(it.date)) + '</span><span>' + ED_TIME[ed] + '</span></p></header>';

    html += tape(it.tape, it.tape_note);

    html += '<section class="front"><div><h2>' + esc(it.headline) + '</h2>' +
      (it.deck ? '<p class="deck">' + esc(it.deck) + '</p>' : '') +
      (it.published_at ? '<p class="byline">' + esc(fmtStamp(it.published_at)) + ' 截稿</p>' : '') + '</div>';
    if (it.brief && it.brief.length) {
      html += '<aside class="brief"><h3>速览</h3><ul>' + it.brief.map(function (b) { return '<li>' + esc(b) + '</li>'; }).join('') + '</ul></aside>';
    }
    html += '</section>';

    html += secUpcoming(it.upcoming) + secMarkets(it.markets) + secAi(it.ai) + secChina(it.china) + secPolicy(it.policy);

    html += '<footer class="foot">';
    if (it.sources && it.sources.length) {
      html += '<strong>资料来源</strong><ol>' + it.sources.map(function (s) {
        var u = safeUrl(s.url);
        return '<li>' + (u ? '<a href="' + esc(u) + '" target="_blank" rel="noopener noreferrer">' + esc(s.title || u) + '</a>' : esc(s.title)) + '</li>';
      }).join('') + '</ol>';
    }
    html += '<p>本报为个人研究记录，行情与判断均可能出错，不构成投资建议。</p></footer>';

    app.innerHTML = html;
    if (timer) clearInterval(timer);
    tick();
    timer = setInterval(tick, 1000);
    window.scrollTo(0, 0);

    document.getElementById('arc').onclick = openArchive;
    if (older) document.getElementById('prev').onclick = function () { go(older.id); };
    if (newer) document.getElementById('next').onclick = function () { go(newer.id); };
  }

  function go(id) { location.hash = '#/' + id; }

  function openArchive() {
    var cur = currentId();
    var byDate = {};
    var order = [];
    index.forEach(function (x) {
      if (!byDate[x.date]) { byDate[x.date] = []; order.push(x.date); }
      byDate[x.date].push(x);
    });
    listEl.innerHTML = order.map(function (d) {
      var items = byDate[d].slice().sort(function (a, b) { return a.edition === 'pm' ? -1 : 1; }); // 晚报在上
      var wd = new Intl.DateTimeFormat('zh-CN', { timeZone: 'UTC', weekday: 'long' }).format(new Date(d + 'T12:00:00Z'));
      return '<div class="arc-day"><div class="d">' + esc(fmtShort(d)) + '<small>' + esc(d.split('-')[0]) + ' ' + esc(wd) + '</small></div><div>' +
        items.map(function (x) {
          return '<a href="#/' + esc(x.id) + '"' + (x.id === cur ? ' class="cur"' : '') + '><span class="t">' + ED[x.edition] + '</span>' + esc(x.headline) + '</a>';
        }).join('') + '</div></div>';
    }).join('');
    if (typeof dlg.showModal === 'function') dlg.showModal(); else dlg.setAttribute('open', '');
  }
  listEl.addEventListener('click', function (e) {
    if (e.target.closest('a')) dlg.close();
  });

  function currentId() {
    var m = location.hash.match(/^#\/([\w-]+)$/);
    return m ? m[1] : (index[0] && index[0].id);
  }

  function fail(msg) { app.innerHTML = '<p class="empty">' + esc(msg) + '</p>'; }

  function load() {
    var id = currentId();
    if (!id) return fail('首期还没有发布，请稍后再来。');
    fetch('issues/' + encodeURIComponent(id) + '.json', { cache: 'no-cache' })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(renderIssue)
      .catch(function () { fail('找不到这一期（' + id + '）。点右上角"往期"看有哪些。'); });
  }

  fetch('issues/index.json', { cache: 'no-cache' })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (j) { index = j.issues || []; load(); })
    .catch(function () { fail('读不到期刊目录，刷新一下试试；还不行说明服务器有问题。'); });

  window.addEventListener('hashchange', load);
})();
