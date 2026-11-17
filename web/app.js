const $ = id => document.getElementById(id);
const canvas = $('scene'), ctx = canvas.getContext('2d');
const plot = $('plot'), plotCtx = plot.getContext('2d');
let socket, state, previous, receivedAt = 0, connected = false, reconnecting = false;
let trail = [], history = [], flightId, follow = false, drag = null, padPreview = null;
let camera = {x: 0, y: 0, zoom: 1}, width = 0, height = 0, needsFit = true;
let noticeTimer, lastFrame = performance.now();
const mint = '#a1cfb6', muted = '#8d9ba9';

function notify(text) {
  $('message').textContent = text;
  $('message').hidden = false;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { $('message').hidden = true; }, 5500);
}
function command(action, extra = {}) {
  if (!connected || socket.readyState !== WebSocket.OPEN) {
    notify('Connection unavailable. Start the Python server and reconnect.');
    return false;
  }
  socket.send(JSON.stringify({action, ...extra}));
  return true;
}
function connect() {
  socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`);
  socket.onopen = () => {
    connected = true;
    $('connection').textContent = 'Connected';
    $('connection-dot').classList.add('online');
    needsFit = true;
    if (reconnecting) notify('Reconnected. A new flight session is ready.');
  };
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.type === 'error') { padPreview = null; notify(message.message); return; }
    if (message.type === 'csv') { download(message); return; }
    if (message.type !== 'state') return;
    previous = state;
    state = message;
    receivedAt = performance.now();
    if (flightId !== state.flight_id) {
      flightId = state.flight_id;
      trail = []; history = []; previous = state;
    }
    if (message.trail) trail = message.trail;
    if (message.history) history = message.history;
    if (needsFit) { fit(); needsFit = false; }
    updateUI();
  };
  socket.onclose = () => {
    connected = false; previous = null;
    $('connection').textContent = 'Disconnected · retrying';
    $('connection-dot').classList.remove('online');
    $('status').textContent = 'Disconnected';
    $('status-detail').textContent = 'Restart the Python server to reconnect.';
    for (const id of ['launch', 'pause', 'stop', 'reset', 'export', 'apply-pad', 'pad-x', 'pad-y', 'settings-file']) $(id).disabled = true;
    reconnecting = true;
    setTimeout(connect, 1500);
  };
  socket.onerror = () => socket.close();
}
function download(message) {
  const url = URL.createObjectURL(new Blob([message.data], {type: 'text/csv;charset=utf-8'}));
  const link = document.createElement('a');
  link.href = url; link.download = message.filename;
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function updateUI() {
  const t = state.telemetry, ready = state.state === 'placement';
  const active = ['running', 'paused'].includes(state.state);
  const done = state.state === 'finished';
  const outcomes = {landed: 'Landed', crashed: 'Crashed', timeout: 'Time limit reached'};
  $('status').textContent = done ? outcomes[state.outcome] : ready ? 'Ready' : state.state === 'paused' ? 'Paused' : 'In flight';
  $('status').style.color = done && state.outcome !== 'landed' ? '#e4ac8c' : ready ? '' : mint;
  $('time').textContent = `T+ ${state.elapsed.toFixed(2).padStart(5, '0')} s`;
  $('status-detail').textContent = done ? 'Export this flight or end it to adjust the pad.' : ready ? 'Place the target, then launch.' : state.state === 'paused' ? 'Physics paused. Camera controls remain available.' : 'Autopilot controlling thrust and attitude.';
  $('altitude').textContent = t.altitude.toFixed(1);
  $('vy').textContent = t.vel_y.toFixed(1);
  $('vx').textContent = t.vel_x.toFixed(1);
  $('angle').textContent = (((t.angle + 180) % 360) - 180).toFixed(1);
  $('offset').textContent = (state.platform.x - t.x).toFixed(1);
  $('fuel').textContent = `${(t.fuel_pct * 100).toFixed(0)}%`;
  $('fuel-bar').value = t.fuel_pct * 100;
  $('fuel-bar').classList.toggle('low-fuel', t.fuel_pct < .2);
  $('engine').textContent = t.thrusting ? 'Engine firing' : 'Engine idle';
  $('engine').style.color = t.thrusting ? mint : '';
  $('throttle').textContent = `${(state.throttle * 100).toFixed(0)}% thrust`;
  const phases = ['launch', 'ascent', 'coast', 'descent', 'terminal'];
  const index = state.outcome === 'landed' ? 5 : phases.indexOf(state.phase);
  [...$('phases').children].forEach((element, i) => {
    element.classList.toggle('done', i < index);
    element.classList.toggle('current', i === index);
  });
  $('phase').textContent = ready ? 'Awaiting launch' : done ? outcomes[state.outcome] : state.phase[0].toUpperCase() + state.phase.slice(1);
  $('launch').disabled = !ready || !connected;
  $('pause').disabled = !active || !connected;
  $('pause').innerHTML = `${state.state === 'paused' ? 'Resume' : 'Pause'} <kbd>Space</kbd>`;
  $('stop').disabled = ready || !connected;
  $('reset').disabled = !connected;
  $('export').disabled = !state.samples || !connected;
  for (const id of ['pad-x', 'pad-y', 'apply-pad', 'settings-file']) $(id).disabled = !ready || !connected;
  if (!drag && !padPreview) {
    if (document.activeElement !== $('pad-x')) $('pad-x').value = Math.round(state.platform.x);
    if (document.activeElement !== $('pad-y')) $('pad-y').value = Math.round(state.platform.y);
  }
  $('settings-values').replaceChildren(...Object.entries(state.settings).map(([key, value]) => {
    const row = document.createElement('div'), dt = document.createElement('dt'), dd = document.createElement('dd');
    dt.textContent = key.replaceAll('_', ' '); dd.textContent = Number(value).toFixed(3);
    row.append(dt, dd); return row;
  }));
  $('scene-hint').textContent = ready ? 'Drag the landing pad to place it. Scroll to zoom.' : done ? 'Flight complete. Export CSV to keep the recording.' : state.state === 'paused' ? 'Paused. Press Space to resume.' : 'Space to pause · C to follow · F to fit';
  $('plot-time').textContent = `${state.elapsed.toFixed(1)} s`;
}
function fit() {
  if (!state || !width || !height) return;
  follow = false; $('follow').setAttribute('aria-pressed', 'false');
  const p = padPreview || state.platform;
  const left = Math.min(220, p.x - 150) - 100, right = Math.max(420, p.x + 150) + 100;
  const top = Math.min(0, p.y - 650), bottom = 660;
  const zoom = Math.max(.1, Math.min(1.6, (width - 60) / (right - left), (height - 95) / (bottom - top)));
  camera = {zoom, x: width / 2 - (left + right) / 2 * zoom, y: height / 2 - (top + bottom) / 2 * zoom};
}
function zoomAt(x, y, factor) {
  const next = Math.max(.1, Math.min(5, camera.zoom * factor));
  const ratio = next / camera.zoom;
  camera.x = x - (x - camera.x) * ratio; camera.y = y - (y - camera.y) * ratio; camera.zoom = next;
}
function sizeCanvas(target, context) {
  const rect = target.getBoundingClientRect(), dpr = Math.min(devicePixelRatio || 1, 2);
  const w = Math.round(rect.width * dpr), h = Math.round(rect.height * dpr);
  if (target.width !== w || target.height !== h) { target.width = w; target.height = h; }
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  return rect;
}
function line(context, color, points, lineWidth = 1) {
  context.beginPath(); context.strokeStyle = color; context.lineWidth = lineWidth;
  points.forEach(([x, y], i) => i ? context.lineTo(x, y) : context.moveTo(x, y)); context.stroke();
}
function polygon(points, fill) {
  ctx.beginPath(); points.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
  ctx.closePath(); ctx.fillStyle = fill; ctx.fill();
}
function deck(x, y, w, title, target = false) {
  ctx.fillStyle = '#394857';
  ctx.fillRect(x - w * .35 - 3, y, 6, Math.max(0, 600 - y));
  ctx.fillRect(x + w * .35 - 3, y, 6, Math.max(0, 600 - y));
  ctx.fillStyle = target ? '#596c73' : '#53616d'; ctx.fillRect(x - w / 2, y, w, 14);
  ctx.fillStyle = target ? mint : '#a9b4be'; ctx.fillRect(x - w / 2 + 4, y + 2, w - 8, 2);
  ctx.font = `${Math.max(10, 10 / camera.zoom)}px system-ui`; ctx.fillStyle = muted; ctx.textAlign = 'center';
  ctx.fillText(title, x, y + 33 / camera.zoom);
  if (target) {
    const d = 7 / camera.zoom;
    line(ctx, mint, [[x - d, y - 9], [x + d, y - 9]]);
    line(ctx, mint, [[x, y - 9 - d], [x, y - 9 + d]]);
    if (state.state === 'placement') {
      ctx.setLineDash([4 / camera.zoom, 5 / camera.zoom]);
      ctx.strokeStyle = '#668c7d'; ctx.strokeRect(x - w / 2 - 8, y - 8, w + 16, 30); ctx.setLineDash([]);
    }
  }
}
function render(now) {
  const dt = Math.min((now - lastFrame) / 1000, .1); lastFrame = now;
  const rect = sizeCanvas(canvas, ctx);
  if (width !== rect.width || height !== rect.height) {
    width = rect.width; height = rect.height;
    if (!drag) fit();
  }
  ctx.fillStyle = '#10151d'; ctx.fillRect(0, 0, width, height);
  if (state) {
    const t = state.telemetry;
    const mix = connected && state.state === 'running' && previous ? Math.min(1, (now - receivedAt) / 33.33) : 1;
    const x = previous ? previous.telemetry.x + (t.x - previous.telemetry.x) * mix : t.x;
    const y = previous ? previous.telemetry.y + (t.y - previous.telemetry.y) * mix : t.y;
    if (follow) {
      const blend = 1 - Math.exp(-7 * dt);
      camera.x += (width / 2 - x * camera.zoom - camera.x) * blend;
      camera.y += (height / 2 - y * camera.zoom - camera.y) * blend;
    }
    const z = camera.zoom;
    const grid = 60 * z;
    for (let gx = camera.x % grid; gx < width; gx += grid) line(ctx, '#1c2733', [[gx, 0], [gx, height]]);
    for (let gy = camera.y % grid; gy < height; gy += grid) line(ctx, '#1c2733', [[0, gy], [width, gy]]);
    ctx.save(); ctx.translate(camera.x, camera.y); ctx.scale(z, z);
    ctx.fillStyle = '#19232c'; ctx.fillRect(-camera.x / z, 600, width / z, Math.max(0, (height - camera.y) / z - 600));
    line(ctx, '#52616b', [[-camera.x / z, 600], [(width - camera.x) / z, 600]], 1 / z);
    deck(320, 566, 130, 'Launch pad');
    const p = padPreview || state.platform;
    deck(p.x, p.y - 16, 300, 'Landing pad', true);
    if (trail.length > 1) line(ctx, '#63887e', [...trail, [x, y]], 1.4 / z);
    ctx.save(); ctx.translate(x, y); ctx.rotate(t.angle * Math.PI / 180);
    if (t.thrusting && state.state === 'running' && connected) {
      const flame = 35 + state.throttle * 30 + Math.sin(now / 35) * 5;
      polygon([[-8, 39], [0, 39 + flame], [8, 39]], '#e5a160');
      polygon([[-4, 39], [0, 39 + flame * .65], [4, 39]], '#ffdfad');
    }
    const body = t.crashed ? '#c6806d' : t.landed ? '#94c7ab' : '#d1d8df';
    ctx.fillStyle = body; ctx.fillRect(-11, -36, 22, 72);
    polygon([[-11, -36], [0, -60], [11, -36]], '#8c9da9');
    polygon([[-11, 24], [-23, 48], [-11, 36]], '#899da9');
    polygon([[11, 24], [23, 48], [11, 36]], '#899da9');
    ctx.fillStyle = '#283340'; ctx.fillRect(-5, -14, 10, 30); ctx.fillRect(-8, 36, 16, 5);
    ctx.restore(); ctx.restore();
    const sx = x * z + camera.x, sy = y * z + camera.y;
    if (sx < 15 || sx > width - 15 || sy < 35 || sy > height - 45) {
      const mx = Math.max(40, Math.min(width - 40, sx)), my = Math.max(55, Math.min(height - 65, sy));
      ctx.strokeStyle = mint; ctx.beginPath(); ctx.arc(mx, my, 7, 0, Math.PI * 2); ctx.stroke();
      ctx.fillStyle = mint; ctx.font = '10px system-ui'; ctx.textAlign = 'center'; ctx.fillText('Rocket · C to follow', mx, my + 23);
    }
    $('zoom').textContent = `${Math.round(z * 100)}%`;
    renderPlot();
  }
  requestAnimationFrame(render);
}
function renderPlot() {
  const rect = sizeCanvas(plot, plotCtx), w = rect.width, h = rect.height;
  plotCtx.clearRect(0, 0, w, h);
  const maxAlt = Math.max(100, ...history.map(row => row[1]));
  const maxTime = Math.max(1, state.elapsed);
  for (let i = 1; i <= 3; i++) line(plotCtx, '#27313c', [[0, h * i / 4], [w, h * i / 4]]);
  if (history.length > 1) line(plotCtx, mint, history.map(row => [row[0] / maxTime * w, h - 8 - row[1] / maxAlt * (h - 16)]), 1.3);
  $('plot-range').textContent = history.length ? `0–${Math.ceil(maxAlt)} px` : 'Waiting for flight';
}
function point(event) { const r = canvas.getBoundingClientRect(); return {x: event.clientX - r.left, y: event.clientY - r.top}; }
function world(point) { return {x: (point.x - camera.x) / camera.zoom, y: (point.y - camera.y) / camera.zoom}; }
function applyPad(x, y) {
  if (!state || state.state !== 'placement') return;
  x = Math.round(Math.max(-1500, Math.min(4000, x))); y = Math.round(Math.max(50, Math.min(600, y)));
  $('pad-x').value = x; $('pad-y').value = y;
  command('configure', {x, y});
}
canvas.addEventListener('pointerdown', event => {
  if (!state || ![0, 1].includes(event.button)) return;
  event.preventDefault(); canvas.focus();
  const p = point(event), w = world(p), target = state.platform;
  const onPad = connected && event.button === 0 && state.state === 'placement' && Math.abs(w.x - target.x) < 170 && Math.abs(w.y - target.surface_y) < 30 / camera.zoom;
  drag = {mode: onPad ? 'pad' : 'pan', start: p, origin: {...camera}, pad: {...target}};
  canvas.setPointerCapture(event.pointerId);
  if (!onPad) { follow = false; $('follow').setAttribute('aria-pressed', 'false'); }
});
canvas.addEventListener('pointermove', event => {
  if (!drag) return;
  const p = point(event), dx = p.x - drag.start.x, dy = p.y - drag.start.y;
  if (drag.mode === 'pad') {
    padPreview = {x: Math.max(-1500, Math.min(4000, drag.pad.x + dx / camera.zoom)), y: Math.max(50, Math.min(600, drag.pad.y + dy / camera.zoom))};
    $('pad-x').value = Math.round(padPreview.x); $('pad-y').value = Math.round(padPreview.y);
  } else { camera.x = drag.origin.x + dx; camera.y = drag.origin.y + dy; }
});
canvas.addEventListener('pointerup', () => {
  if (drag?.mode === 'pad' && padPreview) applyPad(padPreview.x, padPreview.y);
  drag = null; padPreview = null;
});
canvas.addEventListener('pointercancel', () => { drag = null; padPreview = null; });
canvas.addEventListener('wheel', event => { event.preventDefault(); const p = point(event); zoomAt(p.x, p.y, Math.exp(-event.deltaY * .0015)); }, {passive: false});
$('fit').onclick = fit;
$('follow').onclick = () => { follow = !follow; $('follow').setAttribute('aria-pressed', String(follow)); };
$('zoom-in').onclick = () => zoomAt(width / 2, height / 2, 1.2);
$('zoom-out').onclick = () => zoomAt(width / 2, height / 2, 1 / 1.2);
for (const action of ['launch', 'pause', 'stop', 'reset', 'export']) $(action).onclick = () => command(action);
$('reset').addEventListener('click', () => { needsFit = true; $('settings-name').textContent = 'Controller settings retained'; });
$('pad-form').onsubmit = event => {
  event.preventDefault();
  if ($('pad-form').reportValidity()) command('configure', {x: Number($('pad-x').value), y: Number($('pad-y').value)});
};
$('settings-file').onchange = async event => {
  const file = event.target.files[0]; if (!file) return;
  try {
    if (file.size > 32768) throw new Error('Settings file must be smaller than 32 KB.');
    const settings = JSON.parse(await file.text());
    const keys = ['attitude_scale', 'lateral_position_gain', 'vertical_gain', 'terminal_speed'];
    if (!settings || Array.isArray(settings) || Object.keys(settings).length !== keys.length || !keys.every(key => typeof settings[key] === 'number' && Number.isFinite(settings[key]) && settings[key] > 0)) throw new Error('Select a controller settings JSON from tune_controller.py.');
    if (command('configure', {settings})) $('settings-name').textContent = file.name;
  } catch (error) { notify(error.message); }
  event.target.value = '';
};
$('help').onclick = () => $('help-dialog').showModal();
$('close-help').onclick = () => $('help-dialog').close();
window.addEventListener('keydown', event => {
  if (event.target.closest('input, textarea, select, button, summary') || $('help-dialog').open || event.ctrlKey || event.metaKey || event.altKey) return;
  const key = event.key.toLowerCase();
  const actions = {enter: 'launch', ' ': 'pause', r: 'stop'};
  if (actions[key]) {
    event.preventDefault(); if (!event.repeat && !$(actions[key]).disabled) $(actions[key]).click();
  } else if (key === 'f') fit();
  else if (key === 'c' && !event.repeat) $('follow').click();
  else if (['+', '=', '-'].includes(key)) { event.preventDefault(); zoomAt(width / 2, height / 2, key === '-' ? 1 / 1.2 : 1.2); }
  else if (['w', 'a', 's', 'd'].includes(key) && state?.state === 'placement') {
    event.preventDefault(); const step = event.shiftKey ? 20 : 5;
    applyPad(state.platform.x + (key === 'a' ? -step : key === 'd' ? step : 0), state.platform.y + (key === 'w' ? -step : key === 's' ? step : 0));
  } else if (key === '?') $('help-dialog').showModal();
});
connect();
requestAnimationFrame(render);
