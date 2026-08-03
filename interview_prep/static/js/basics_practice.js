let currentBasicsQuestion = null;
let selectedOptionIndex = null;
let answerChecked = false;

const BASICS_SOLVED_KEY_PREFIX = 'interview_prep_solved_basics_';

function isBasicsSolved(id) {
  return localStorage.getItem(BASICS_SOLVED_KEY_PREFIX + id) === '1';
}
function markBasicsSolved(id) {
  localStorage.setItem(BASICS_SOLVED_KEY_PREFIX + id, '1');
}

function renderQuestionList() {
  const list = document.getElementById('question-list');
  list.innerHTML = '';
  let lastCategory = null;
  BASICS_QUESTIONS.forEach((q) => {
    if (q.category !== lastCategory) {
      const header = document.createElement('li');
      header.className = 'category-header';
      header.textContent = q.category;
      list.appendChild(header);
      lastCategory = q.category;
    }
    const li = document.createElement('li');
    li.className = 'question-item' + (isBasicsSolved(q.id) ? ' solved' : '');
    li.dataset.id = q.id;
    li.innerHTML = `<span class="check">${isBasicsSolved(q.id) ? '✅' : '⬜'}</span>
      <span class="q-title">${q.title}</span>`;
    li.addEventListener('click', () => selectQuestion(q.id));
    list.appendChild(li);
  });
}

function selectQuestion(id) {
  currentBasicsQuestion = BASICS_QUESTIONS.find((q) => q.id === id);
  selectedOptionIndex = null;
  answerChecked = false;
  document.querySelectorAll('.question-item').forEach((el) => {
    el.classList.toggle('active', el.dataset.id === id);
  });
  document.getElementById('q-title').textContent =
    `[${currentBasicsQuestion.category}] ${currentBasicsQuestion.title}`;
  document.getElementById('q-prompt').textContent = currentBasicsQuestion.question;
  document.getElementById('feedback').innerHTML = '';
  renderOptions();
}

function renderOptions() {
  const container = document.getElementById('options-area');
  container.innerHTML = '';
  currentBasicsQuestion.options.forEach((opt, idx) => {
    const div = document.createElement('div');
    div.className = 'option-item';
    if (selectedOptionIndex === idx) div.classList.add('selected');
    if (answerChecked) {
      if (idx === currentBasicsQuestion.correctIndex) div.classList.add('correct');
      else if (idx === selectedOptionIndex) div.classList.add('incorrect');
    }
    div.textContent = String.fromCharCode(65 + idx) + '. ' + opt;
    div.addEventListener('click', () => {
      if (answerChecked) return;
      selectedOptionIndex = idx;
      renderOptions();
    });
    container.appendChild(div);
  });
}

function checkAnswer() {
  if (!currentBasicsQuestion) return;
  const feedback = document.getElementById('feedback');
  if (selectedOptionIndex === null) {
    feedback.innerHTML = '<p class="fail">先选一个选项吧</p>';
    return;
  }
  answerChecked = true;
  renderOptions();
  const correct = selectedOptionIndex === currentBasicsQuestion.correctIndex;
  if (correct) {
    feedback.innerHTML = `<p class="pass">✅ 正确!</p><p class="explanation">${currentBasicsQuestion.explanation}</p>`;
    markBasicsSolved(currentBasicsQuestion.id);
    renderQuestionList();
    document.querySelectorAll('.question-item').forEach((el) => {
      el.classList.toggle('active', el.dataset.id === currentBasicsQuestion.id);
    });
  } else {
    feedback.innerHTML = `<p class="fail">❌ 不对,正确答案是 ${String.fromCharCode(
      65 + currentBasicsQuestion.correctIndex
    )}</p><p class="explanation">${currentBasicsQuestion.explanation}</p>`;
  }
}

function showExplanation() {
  if (!currentBasicsQuestion) return;
  answerChecked = true;
  selectedOptionIndex = selectedOptionIndex === null ? currentBasicsQuestion.correctIndex : selectedOptionIndex;
  renderOptions();
  const feedback = document.getElementById('feedback');
  feedback.innerHTML = `<p class="explanation">${currentBasicsQuestion.explanation}</p>`;
}

window.addEventListener('DOMContentLoaded', () => {
  renderQuestionList();
  document.getElementById('check-btn').addEventListener('click', checkAnswer);
  document.getElementById('solution-btn').addEventListener('click', showExplanation);
  if (BASICS_QUESTIONS.length) selectQuestion(BASICS_QUESTIONS[0].id);
});
