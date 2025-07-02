// static/script.js

async function fetchStatus() {
  const res = await fetch('/status');
  const data = await res.json();
  document.getElementById('active-source').textContent = data.active || 'None';

  const list = document.getElementById('source-list');
  list.innerHTML = '';

  Object.entries(data.sources).forEach(([name, path]) => {
    const li = document.createElement('li');
    li.textContent = `${name}: ${path} `;

    // Switch Button
    const switchBtn = document.createElement('button');
    switchBtn.textContent = 'Switch To';
    switchBtn.onclick = () => switchSource(name);
    li.appendChild(switchBtn);

    // Remove Button
    const removeBtn = document.createElement('button');
    removeBtn.textContent = '🗑 Remove';
    removeBtn.style.backgroundColor = '#f55';
    removeBtn.onclick = () => removeSource(name);
    li.appendChild(removeBtn);

    list.appendChild(li);
  });
}

async function switchSource(name) {
  await fetch('/switch_source', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name })
  });
  await fetchStatus();
}

async function removeSource(name) {
  await fetch('/remove_source', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name })
  });
  await fetchStatus();
}

document.getElementById('add-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const name = document.getElementById('source-name').value;
  const path = document.getElementById('source-path').value;
  await fetch('/add_source', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, path })
  });
  document.getElementById('add-form').reset();
  await fetchStatus();
});

fetchStatus();
