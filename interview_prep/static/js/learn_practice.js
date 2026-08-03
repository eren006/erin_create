const LEARN_READ_KEY_PREFIX = 'interview_prep_read_learn_';

function isLearnRead(id) {
  return localStorage.getItem(LEARN_READ_KEY_PREFIX + id) === '1';
}
function markLearnRead(id) {
  localStorage.setItem(LEARN_READ_KEY_PREFIX + id, '1');
}

function renderTopicList() {
  const list = document.getElementById('topic-list');
  list.innerHTML = '';
  let lastCategory = null;
  LEARN_TOPICS.forEach((t) => {
    if (t.category !== lastCategory) {
      const header = document.createElement('li');
      header.className = 'category-header';
      header.textContent = t.category;
      list.appendChild(header);
      lastCategory = t.category;
    }
    const li = document.createElement('li');
    li.className = 'question-item' + (isLearnRead(t.id) ? ' solved' : '');
    li.dataset.id = t.id;
    li.innerHTML = `<span class="check">${isLearnRead(t.id) ? '✅' : '⬜'}</span>
      <span class="q-title">${t.title}</span>`;
    li.addEventListener('click', () => selectTopic(t.id));
    list.appendChild(li);
  });
}

function selectTopic(id) {
  const topic = LEARN_TOPICS.find((t) => t.id === id);
  if (!topic) return;
  document.querySelectorAll('.question-item').forEach((el) => {
    el.classList.toggle('active', el.dataset.id === id);
  });
  document.getElementById('topic-title').textContent = `[${topic.category}] ${topic.title}`;
  document.getElementById('topic-summary').textContent = topic.summary || '';
  document.getElementById('topic-body').innerHTML = topic.html;
  markLearnRead(id);
  renderTopicList();
  document.querySelectorAll('.question-item').forEach((el) => {
    el.classList.toggle('active', el.dataset.id === id);
  });
  window.scrollTo({ top: 0, behavior: 'instant' });
}

window.addEventListener('DOMContentLoaded', () => {
  renderTopicList();
  if (LEARN_TOPICS.length) selectTopic(LEARN_TOPICS[0].id);
});
