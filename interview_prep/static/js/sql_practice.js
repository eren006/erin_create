let SQL_ENGINE = null;
let currentSqlQuestion = null;

const SOLVED_KEY_PREFIX = 'interview_prep_solved_sql_';

function isSqlSolved(id) {
  return localStorage.getItem(SOLVED_KEY_PREFIX + id) === '1';
}
function markSqlSolved(id) {
  localStorage.setItem(SOLVED_KEY_PREFIX + id, '1');
}

async function initSqlEngine() {
  const initSqlJs = window.initSqlJs;
  const SQL = await initSqlJs({
    locateFile: (file) => `https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/${file}`,
  });
  SQL_ENGINE = SQL;
  document.getElementById('engine-status').textContent = '就绪';
}

function freshDb() {
  const db = new SQL_ENGINE.Database();
  db.run(SQL_SCHEMA_DATA);
  return db;
}

function renderQuestionList() {
  const list = document.getElementById('question-list');
  list.innerHTML = '';
  SQL_QUESTIONS.forEach((q) => {
    const li = document.createElement('li');
    li.className = 'question-item' + (isSqlSolved(q.id) ? ' solved' : '');
    li.dataset.id = q.id;
    li.innerHTML = `<span class="check">${isSqlSolved(q.id) ? '✅' : '⬜'}</span>
      <span class="q-title">${q.title}</span>
      <span class="q-diff">${q.difficulty}</span>`;
    li.addEventListener('click', () => selectQuestion(q.id));
    list.appendChild(li);
  });
}

function selectQuestion(id) {
  currentSqlQuestion = SQL_QUESTIONS.find((q) => q.id === id);
  document.querySelectorAll('.question-item').forEach((el) => {
    el.classList.toggle('active', el.dataset.id === id);
  });
  document.getElementById('q-title').textContent = currentSqlQuestion.title;
  document.getElementById('q-prompt').textContent = currentSqlQuestion.prompt;
  document.getElementById('q-hint').textContent = currentSqlQuestion.schemaHint || '';
  document.getElementById('code-input').value = currentSqlQuestion.starter;
  document.getElementById('result-area').innerHTML = '';
  document.getElementById('feedback').innerHTML = '';
}

function renderResultTable(container, columns, values) {
  if (!columns.length) {
    container.innerHTML = '<p class="muted">(空结果)</p>';
    return;
  }
  const table = document.createElement('table');
  const thead = document.createElement('thead');
  thead.innerHTML = '<tr>' + columns.map((c) => `<th>${c}</th>`).join('') + '</tr>';
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  values.forEach((row) => {
    const tr = document.createElement('tr');
    tr.innerHTML = row.map((v) => `<td>${v === null ? 'NULL' : v}</td>`).join('');
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  container.innerHTML = '';
  container.appendChild(table);
}

function normalizeValue(v) {
  if (typeof v === 'number' && !Number.isInteger(v)) return Math.round(v * 1000) / 1000;
  return v;
}

function rowsToComparableStrings(values) {
  return values.map((row) => JSON.stringify(row.map(normalizeValue)));
}

function runUserQuery() {
  if (!currentSqlQuestion) return;
  const sql = document.getElementById('code-input').value;
  const resultArea = document.getElementById('result-area');
  const feedback = document.getElementById('feedback');
  feedback.innerHTML = '';
  try {
    const db = freshDb();
    const res = db.exec(sql);
    db.close();
    if (!res.length) {
      resultArea.innerHTML = '<p class="muted">查询没有返回任何列(可能是空结果集)</p>';
      return;
    }
    renderResultTable(resultArea, res[0].columns, res[0].values);
  } catch (e) {
    resultArea.innerHTML = `<p class="error">出错了: ${e.message}</p>`;
  }
}

function checkAnswer() {
  if (!currentSqlQuestion) return;
  const sql = document.getElementById('code-input').value;
  const feedback = document.getElementById('feedback');
  const resultArea = document.getElementById('result-area');

  let userRes, refRes;
  try {
    const db1 = freshDb();
    userRes = db1.exec(sql);
    db1.close();
  } catch (e) {
    resultArea.innerHTML = `<p class="error">出错了: ${e.message}</p>`;
    feedback.innerHTML = '<p class="fail">❌ 你的查询执行出错,先运行看看报错信息</p>';
    return;
  }

  const db2 = freshDb();
  refRes = db2.exec(currentSqlQuestion.solution);
  db2.close();

  if (!userRes.length) {
    resultArea.innerHTML = '<p class="muted">(空结果)</p>';
    feedback.innerHTML = '<p class="fail">❌ 查询没有返回结果</p>';
    return;
  }
  renderResultTable(resultArea, userRes[0].columns, userRes[0].values);

  const userCols = userRes[0].columns;
  const refCols = refRes[0].columns;
  let userRows = rowsToComparableStrings(userRes[0].values);
  let refRows = rowsToComparableStrings(refRes[0].values);

  if (!currentSqlQuestion.orderMatters) {
    userRows = [...userRows].sort();
    refRows = [...refRows].sort();
  }

  const colCountMatch = userCols.length === refCols.length;
  const rowsMatch =
    userRows.length === refRows.length && userRows.every((r, i) => r === refRows[i]);

  if (colCountMatch && rowsMatch) {
    feedback.innerHTML = '<p class="pass">✅ 正确!</p>';
    markSqlSolved(currentSqlQuestion.id);
    renderQuestionList();
    document.querySelectorAll('.question-item').forEach((el) => {
      el.classList.toggle('active', el.dataset.id === currentSqlQuestion.id);
    });
  } else {
    feedback.innerHTML = `<p class="fail">❌ 结果不对。期望 ${refRows.length} 行 ${refCols.length} 列,你返回了 ${userRows.length} 行 ${userCols.length} 列。</p>`;
  }
}

function showSolution() {
  if (!currentSqlQuestion) return;
  document.getElementById('code-input').value = currentSqlQuestion.solution;
}

window.addEventListener('DOMContentLoaded', () => {
  renderQuestionList();
  document.getElementById('run-btn').addEventListener('click', runUserQuery);
  document.getElementById('check-btn').addEventListener('click', checkAnswer);
  document.getElementById('solution-btn').addEventListener('click', showSolution);
  initSqlEngine();
  if (SQL_QUESTIONS.length) selectQuestion(SQL_QUESTIONS[0].id);
});
