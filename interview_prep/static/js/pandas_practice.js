let pyodideInstance = null;
let currentPdQuestion = null;

const PD_SOLVED_KEY_PREFIX = 'interview_prep_solved_pd_';

function isPdSolved(id) {
  return localStorage.getItem(PD_SOLVED_KEY_PREFIX + id) === '1';
}
function markPdSolved(id) {
  localStorage.setItem(PD_SOLVED_KEY_PREFIX + id, '1');
}

const PY_HELPERS = `
import json
import pandas as pd
import numpy as np

def _index_is_default_range(idx):
    return list(idx) == list(range(len(idx)))

def _prep(obj):
    if isinstance(obj, pd.Series):
        if _index_is_default_range(obj.index):
            df = obj.to_frame(name=str(obj.name) if obj.name is not None else 'value')
        else:
            df = obj.reset_index()
    elif isinstance(obj, pd.DataFrame):
        df = obj.copy() if _index_is_default_range(obj.index) else obj.reset_index()
    else:
        df = pd.DataFrame({'value': [obj]})
    df.columns = [str(c) for c in df.columns]
    return df

def _to_table(obj):
    df = _prep(obj)
    cols = list(df.columns)
    rows = []
    for _, r in df.iterrows():
        row = []
        for v in r.tolist():
            if isinstance(v, (np.floating, float)):
                row.append(None if pd.isna(v) else round(float(v), 4))
            elif isinstance(v, (np.integer,)):
                row.append(int(v))
            else:
                try:
                    na = bool(pd.isna(v))
                except (TypeError, ValueError):
                    na = False
                row.append(None if na else (v if isinstance(v, (int, str, bool)) else str(v)))
        rows.append(row)
    return {'columns': cols, 'rows': rows}

def _grade(expected, actual, order_matters):
    et = _to_table(expected)
    at = _to_table(actual)
    if et['columns'] != at['columns']:
        return {'ok': False, 'reason': '列不一致。期望列: ' + str(et['columns']) + ', 你的列: ' + str(at['columns'])}
    e_strs = [json.dumps(r, ensure_ascii=False) for r in et['rows']]
    a_strs = [json.dumps(r, ensure_ascii=False) for r in at['rows']]
    if not order_matters:
        e_strs = sorted(e_strs)
        a_strs = sorted(a_strs)
    ok = e_strs == a_strs
    return {'ok': ok, 'reason': None, 'expected_rows': len(e_strs), 'actual_rows': len(a_strs)}

def _run_isolated(code):
    __ns = {'pd': pd, 'np': np, 'sales_df': sales_df.copy(), 'customers_df': customers_df.copy()}
    exec(code, __ns)
    if 'result' not in __ns:
        raise NameError("代码没有给变量 result 赋值")
    return __ns.get('result')
`;

async function initPandasEngine() {
  pyodideInstance = await loadPyodide({
    indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/',
  });
  await pyodideInstance.loadPackage(['pandas', 'numpy']);
  document.getElementById('engine-status').textContent = '就绪';
}

function renderTable(container, columns, rows) {
  if (!columns.length) {
    container.innerHTML = '<p class="muted">(空结果)</p>';
    return;
  }
  const table = document.createElement('table');
  const thead = document.createElement('thead');
  thead.innerHTML = '<tr>' + columns.map((c) => `<th>${c}</th>`).join('') + '</tr>';
  table.appendChild(thead);
  const tbody = document.createElement('tbody');
  rows.forEach((row) => {
    const tr = document.createElement('tr');
    tr.innerHTML = row.map((v) => `<td>${v === null || v === undefined ? 'NaN' : v}</td>`).join('');
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  container.innerHTML = '';
  container.appendChild(table);
}

function renderQuestionList() {
  const list = document.getElementById('question-list');
  list.innerHTML = '';
  PANDAS_QUESTIONS.forEach((q) => {
    const li = document.createElement('li');
    li.className = 'question-item' + (isPdSolved(q.id) ? ' solved' : '');
    li.dataset.id = q.id;
    li.innerHTML = `<span class="check">${isPdSolved(q.id) ? '✅' : '⬜'}</span>
      <span class="q-title">${q.title}</span>
      <span class="q-diff">${q.difficulty}</span>`;
    li.addEventListener('click', () => selectQuestion(q.id));
    list.appendChild(li);
  });
}

function selectQuestion(id) {
  currentPdQuestion = PANDAS_QUESTIONS.find((q) => q.id === id);
  document.querySelectorAll('.question-item').forEach((el) => {
    el.classList.toggle('active', el.dataset.id === id);
  });
  document.getElementById('q-title').textContent = currentPdQuestion.title;
  document.getElementById('q-prompt').textContent = currentPdQuestion.prompt;
  document.getElementById('q-hint').textContent = currentPdQuestion.dataHint || '';
  document.getElementById('code-input').value = currentPdQuestion.starter;
  document.getElementById('result-area').innerHTML = '';
  document.getElementById('feedback').innerHTML = '';
}

async function runUserCode() {
  if (!currentPdQuestion || !pyodideInstance) return;
  const code = document.getElementById('code-input').value;
  const resultArea = document.getElementById('result-area');
  const feedback = document.getElementById('feedback');
  feedback.innerHTML = '';
  pyodideInstance.globals.set('__USER_CODE__', code);
  const script = `${PY_HELPERS}\n${PANDAS_SETUP_CODE}\n_actual = _run_isolated(__USER_CODE__)\njson.dumps({'display': _to_table(_actual)})`;
  try {
    const raw = pyodideInstance.runPython(script);
    const parsed = JSON.parse(raw);
    renderTable(resultArea, parsed.display.columns, parsed.display.rows);
  } catch (e) {
    resultArea.innerHTML = `<p class="error">出错了: ${escapeHtml(e.message)}</p>`;
  }
}

async function checkAnswer() {
  if (!currentPdQuestion || !pyodideInstance) return;
  const code = document.getElementById('code-input').value;
  const resultArea = document.getElementById('result-area');
  const feedback = document.getElementById('feedback');
  feedback.innerHTML = '';
  pyodideInstance.globals.set('__USER_CODE__', code);
  pyodideInstance.globals.set('__REF_CODE__', currentPdQuestion.solution);
  pyodideInstance.globals.set('__ORDER_MATTERS__', !!currentPdQuestion.orderMatters);
  const script = `${PY_HELPERS}\n${PANDAS_SETUP_CODE}
_actual = _run_isolated(__USER_CODE__)
_expected = _run_isolated(__REF_CODE__)
_result = _grade(_expected, _actual, __ORDER_MATTERS__)
json.dumps({'display': _to_table(_actual), 'grade': _result})`;
  try {
    const raw = pyodideInstance.runPython(script);
    const parsed = JSON.parse(raw);
    renderTable(resultArea, parsed.display.columns, parsed.display.rows);
    if (parsed.grade.ok) {
      feedback.innerHTML = '<p class="pass">✅ 正确!</p>';
      markPdSolved(currentPdQuestion.id);
      renderQuestionList();
      document.querySelectorAll('.question-item').forEach((el) => {
        el.classList.toggle('active', el.dataset.id === currentPdQuestion.id);
      });
    } else {
      const reason =
        parsed.grade.reason ||
        `期望 ${parsed.grade.expected_rows} 行,你返回了 ${parsed.grade.actual_rows} 行,内容对不上。`;
      feedback.innerHTML = `<p class="fail">❌ 结果不对。${escapeHtml(reason)}</p>`;
    }
  } catch (e) {
    resultArea.innerHTML = `<p class="error">出错了: ${escapeHtml(e.message)}</p>`;
    feedback.innerHTML = '<p class="fail">❌ 代码执行出错,先运行看看报错信息</p>';
  }
}

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

function showSolution() {
  if (!currentPdQuestion) return;
  document.getElementById('code-input').value = currentPdQuestion.solution;
}

window.addEventListener('DOMContentLoaded', () => {
  renderQuestionList();
  document.getElementById('run-btn').addEventListener('click', runUserCode);
  document.getElementById('check-btn').addEventListener('click', checkAnswer);
  document.getElementById('solution-btn').addEventListener('click', showSolution);
  initPandasEngine();
  if (PANDAS_QUESTIONS.length) selectQuestion(PANDAS_QUESTIONS[0].id);
});
