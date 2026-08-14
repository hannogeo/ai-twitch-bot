'use strict';

const bridge = window.api;
const $ = (sel) => document.querySelector(sel);

const state = {
  config: null,
  version: '',
  running: false,
  update: null,
  authOpen: false,
};

let toastTimer = null;

function toast(msg) {
  const el = $('#toast');
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.hidden = true;
  }, 2200);
}

function openExternal(url) {
  bridge.openExternal(url);
}

async function copyText(text) {
  await bridge.copyText(text);
  toast('Copied to clipboard');
}

// â”€â”€ Log â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const USER_COLORS = ['#cda927', '#A970FF', '#da639b', '#3BCB84', '#56b6c2', '#61afef', '#e5c07b'];

function userColor(name) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return USER_COLORS[h % USER_COLORS.length];
}

function appendLog(payload) {
  const text = payload.text || '';
  const log = $('#log');
  const line = document.createElement('div');
  line.className = 'log-line';

  if (text.startsWith('BOT -> ')) {
    const rest = text.slice(7);
    const idx = rest.indexOf(': ');
    const who = idx >= 0 ? rest.slice(0, idx) : '';
    const msg = idx >= 0 ? rest.slice(idx + 2) : rest;
    line.classList.add('bot');
    const user = document.createElement('span');
    user.className = 'log-user';
    user.textContent = 'AI Twitch Bot';
    const tag = document.createElement('span');
    tag.className = 'bot-tag';
    tag.textContent = 'BOT';
    const p = document.createElement('span');
    p.className = 'log-msg';
    p.textContent = msg;
    line.append(user, tag, p);
    if (text.includes('FAILED')) line.classList.add('err');
  } else if (/^[^:]+: /.test(text)) {
    const idx = text.indexOf(': ');
    const who = text.slice(0, idx);
    const msg = text.slice(idx + 2);
    line.classList.add('chat');
    const user = document.createElement('span');
    user.className = 'log-user';
    user.style.color = userColor(who);
    user.textContent = who;
    const p = document.createElement('span');
    p.className = 'log-msg';
    p.textContent = msg;
    line.append(user, p);
  } else {
    const isError = text.includes('Error') || text.includes('FAILED');
    line.classList.add(isError ? 'sys-err' : 'sys');
    line.textContent = text;
  }

  log.appendChild(line);
  while (log.children.length > 500) log.removeChild(log.firstChild);
  log.scrollTop = log.scrollHeight;
}

// â”€â”€ Status / toggle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function renderStatus() {
  const badge = $('#status-badge');
  const btn = $('#btn-toggle');
  badge.classList.toggle('running', state.running);
  badge.querySelector('.label').textContent = state.running ? 'RUNNING' : 'STOPPED';
  btn.classList.toggle('btn-stop', state.running);
  btn.classList.toggle('btn-start', !state.running);
  btn.textContent = state.running ? '\u25A0 STOP BOT' : '\u25B6 START BOT';
}

async function toggleBot() {
  await bridge.toggleBot();
}

// â”€â”€ Auth â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function accountEl(container, key, title, subtitle) {
  const card = document.createElement('div');
  card.className = 'account-card';

  const head = document.createElement('div');
  head.className = 'account-head';
  const name = document.createElement('span');
  name.className = 'account-name';
  name.textContent = title;
  const status = document.createElement('span');
  status.className = 'account-status';
  head.append(name, status);

  const sub = document.createElement('div');
  sub.className = 'account-sub';
  sub.textContent = subtitle;

  const actions = document.createElement('div');
  actions.className = 'account-actions';

  const signInBtn = document.createElement('button');
  signInBtn.className = 'btn btn-accent';
  signInBtn.textContent = 'Sign in with Twitch';
  signInBtn.addEventListener('click', () => bridge.signIn(key));

  const signOutBtn = document.createElement('button');
  signOutBtn.className = 'btn btn-outline';
  signOutBtn.textContent = 'Sign out';
  signOutBtn.style.display = 'none';
  signOutBtn.addEventListener('click', async () => {
    await bridge.signOut(key);
    toast('Signed out');
  });

  actions.append(signInBtn, signOutBtn);
  card.append(head, sub, actions);

  container.replaceChildren(card);

  return { status, signInBtn, signOutBtn };
}

function renderAuth() {
  const botCfg = state.config.bot;
  const auth = botCfg.TWITCH_AUTH || {};
  const streamer = auth.streamer || {};
  const botAccount = auth.bot || {};

  const s = accountEl(
    $('#account-streamer'),
    'streamer',
    'Streamer Account',
    'The account whose channel the bot chats in. If no bot account is set, the bot also sends messages as this account.'
  );
  const b = accountEl(
    $('#account-bot'),
    'bot',
    'Bot Account (optional)',
    'By default the bot sends messages as you. Sign in a different account here to send messages as it instead.'
  );

  for (const [entry, el] of [[streamer, s], [botAccount, b]]) {
    const name = entry.display_name || entry.login || '';
    if (name) {
      el.status.textContent = `Signed in as @${name}`;
      el.status.classList.add('signed-in');
      el.signInBtn.style.display = 'none';
      el.signOutBtn.style.display = '';
    } else {
      el.status.textContent = 'Not signed in';
      el.status.classList.remove('signed-in');
      el.signInBtn.style.display = '';
      el.signOutBtn.style.display = 'none';
    }
  }
}

function showAuthCode(evt) {
  state.authOpen = true;
  const modal = $('#auth-modal');
  const body = $('#auth-body');
  const cancelBtn = $('#auth-cancel');
  cancelBtn.textContent = 'Cancel';
  cancelBtn.onclick = () => {
    bridge.cancelSignIn();
    closeAuth();
  };
  const uri = evt.verification_uri || 'https://www.twitch.tv/activate';
  body.innerHTML = `
    <div class="steps">
      <div>1. Open the Twitch page:</div>
      <button class="btn btn-accent" id="auth-open">Open twitch.tv/activate</button>
      <button class="btn btn-ghost btn-small" id="auth-copy-url">Copy link</button>
      <div class="url-text">${escapeHtml(uri)}</div>
      <div style="height:8px"></div>
      <div>2. Enter this code:</div>
      <div class="code-row">
        <div class="code">${evt.user_code}</div>
        <button class="btn btn-ghost btn-small" id="auth-copy-code">Copy</button>
      </div>
      <div style="height:8px"></div>
      <div class="muted">Waiting for you to authorize...</div>
    </div>`;
  $('#auth-open').addEventListener('click', () => openExternal(uri));
  $('#auth-copy-url').addEventListener('click', () => copyText(uri));
  $('#auth-copy-code').addEventListener('click', () => copyText(evt.user_code));
  modal.hidden = false;
}

function closeAuth() {
  state.authOpen = false;
  $('#auth-modal').hidden = true;
}

function showAuthError(message) {
  const body = $('#auth-body');
  body.innerHTML = `
    <div style="color:var(--red);font-size:26px">&#9888;</div>
    <div class="muted">${escapeHtml(message)}</div>`;
  const cancelBtn = $('#auth-cancel');
  cancelBtn.textContent = 'Close';
  cancelBtn.onclick = () => closeAuth();
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
}

function confirmDialog(message) {
  return new Promise((resolve) => {
    const modal = document.createElement('div');
    modal.className = 'modal confirm-modal';
    modal.innerHTML = `
      <div class="modal-card">
        <div class="modal-title">Please confirm</div>
        <div class="modal-body">${escapeHtml(message)}</div>
        <div class="modal-actions">
          <button class="btn btn-ghost" data-choice="cancel">Cancel</button>
          <button class="btn btn-accent" data-choice="ok">Confirm</button>
        </div>
      </div>`;
    const finish = (result) => {
      document.removeEventListener('keydown', onKey);
      modal.remove();
      resolve(result);
    };
    const onKey = (e) => {
      if (e.key === 'Escape') finish(false);
    };
    modal.querySelector('[data-choice="cancel"]').addEventListener('click', () => finish(false));
    modal.querySelector('[data-choice="ok"]').addEventListener('click', () => finish(true));
    document.addEventListener('keydown', onKey);
    document.body.appendChild(modal);
  });
}

// â”€â”€ Bot Config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function renderBotConfig() {
  const cfg = state.config.bot;
  $('#sw-conn').checked = !!cfg.CONNECT_MSG_ENABLED;
  $('#sw-disc').checked = !!cfg.DISCONNECT_MSG_ENABLED;
  $('#sw-tag').checked = !!cfg.TRIGGER_TAG;
  $('#sw-cmd').checked = !!cfg.TRIGGER_CMD;
  $('#sw-rep').checked = !!cfg.TRIGGER_REP;
  $('#sw-other-rep').checked = !!cfg.TRIGGER_OTHER_REP;
  $('#in-cmds').value = cfg.COMMANDS || '!ai, !aichat';
  const effNick = nickLabel();
  $('#sw-tag-label').textContent = `Activate on @${effNick || 'Bot'} Tag`;
  renderAuth();
}

function nickLabel() {
  const auth = (state.config.bot.TWITCH_AUTH || {});
  return ((auth.bot && auth.bot.login) || (auth.streamer && auth.streamer.login) || '').replace(/^#/, '');
}

async function saveBot() {
  await bridge.saveBotConfig({
    CONNECT_MSG_ENABLED: $('#sw-conn').checked,
    DISCONNECT_MSG_ENABLED: $('#sw-disc').checked,
    TRIGGER_TAG: $('#sw-tag').checked,
    TRIGGER_CMD: $('#sw-cmd').checked,
    TRIGGER_REP: $('#sw-rep').checked,
    TRIGGER_OTHER_REP: $('#sw-other-rep').checked,
    COMMANDS: $('#in-cmds').value.trim(),
  });
  toast('Bot settings saved');
}

// â”€â”€ AI Config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function renderAiConfig() {
  const cfg = state.config.ai;
  $('#in-key').value = cfg.api_key || '';
  $('#in-instr').value = cfg.system_instruction || '';
  renderContexts();
}

function renderContexts() {
  const list = $('#ctx-list');
  list.replaceChildren();
  const ctx = state.config.ai.chatter_context || {};
  for (const username of Object.keys(ctx).sort()) {
    const info = ctx[username];

    const item = document.createElement('div');
    item.className = 'ctx-item';

    const user = document.createElement('div');
    user.className = 'ctx-user';
    user.textContent = `@${username}`;

    const body = document.createElement('div');
    body.className = 'ctx-body';
    const ta = document.createElement('textarea');
    ta.value = info;
    ta.rows = 2;
    body.appendChild(ta);

    const actions = document.createElement('div');
    actions.className = 'ctx-actions';

    const saveBtn = document.createElement('button');
    saveBtn.className = 'btn btn-ghost btn-small';
    saveBtn.textContent = 'Save';
    saveBtn.addEventListener('click', async () => {
      const next = { ...(state.config.ai.chatter_context || {}) };
      next[username] = ta.value.trim();
      await bridge.setChatterContext(next);
      state.config.ai.chatter_context = next;
      toast('Context saved');
    });

    const delBtn = document.createElement('button');
    delBtn.className = 'btn btn-ghost btn-small';
    delBtn.textContent = 'Remove';
    delBtn.addEventListener('click', async () => {
      if (!(await confirmDialog(`Remove context for @${username}?`))) return;
      const next = { ...(state.config.ai.chatter_context || {}) };
      delete next[username];
      await bridge.setChatterContext(next);
      state.config.ai.chatter_context = next;
      renderContexts();
    });

    actions.append(saveBtn, delBtn);
    item.append(user, body, actions);
    list.appendChild(item);
  }
}

async function saveAi() {
  await bridge.saveAiConfig({
    api_key: $('#in-key').value.trim(),
    system_instruction: $('#in-instr').value.trim(),
  });
  state.config.ai.api_key = $('#in-key').value.trim();
  state.config.ai.system_instruction = $('#in-instr').value.trim();
  toast('AI settings saved');
}

// â”€â”€ Update banner â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function renderUpdate() {
  const banner = $('#update-banner');
  const detail = $('#update-detail');
  const actions = $('#update-actions');
  const u = state.update;

  if (!u) {
    banner.hidden = true;
    return;
  }
  banner.hidden = false;

  if (u.type === 'available') {
    detail.textContent = `Version ${u.version} is available.`;
    actions.innerHTML = '';
    const btn = document.createElement('button');
    btn.className = 'btn btn-accent';
    btn.textContent = 'Download & Install';
    btn.addEventListener('click', () => bridge.startUpdate(u.url));
    actions.appendChild(btn);
  } else if (u.type === 'progress') {
    detail.textContent = `Downloading... ${Math.round(u.percent * 100)}%`;
    actions.innerHTML = `
      <div class="progress-bar"><div class="progress-fill" style="width:${Math.round(u.percent * 100)}%"></div></div>`;
  } else if (u.type === 'installing') {
    detail.textContent = 'Installing...';
    actions.innerHTML = '';
  } else if (u.type === 'error') {
    detail.textContent = `Update failed: ${u.error}`;
    actions.innerHTML = '';
  }
}

// â”€â”€ Views â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function switchView(name) {
  state.view = name;
  for (const tab of document.querySelectorAll('.tab')) {
    tab.classList.toggle('active', tab.dataset.view === name);
  }
  for (const view of document.querySelectorAll('.view')) {
    view.classList.toggle('active', view.id === `view-${name}`);
  }
}

// â”€â”€ Init â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function wireEvents() {
  for (const tab of document.querySelectorAll('.tab')) {
    tab.addEventListener('click', () => switchView(tab.dataset.view));
  }

  $('#btn-toggle').addEventListener('click', toggleBot);
  $('#save-bot').addEventListener('click', saveBot);
  $('#save-ai').addEventListener('click', saveAi);

  $('#ctx-add').addEventListener('click', async () => {
    const user = $('#ctx-user').value.trim().toLowerCase();
    const info = $('#ctx-info').value.trim();
    if (!user || !info) return;
    const next = { ...(state.config.ai.chatter_context || {}), [user]: info };
    await bridge.setChatterContext(next);
    state.config.ai.chatter_context = next;
    $('#ctx-user').value = '';
    $('#ctx-info').value = '';
    renderContexts();
  });

  $('#log-clear').addEventListener('click', async () => {
    if (!(await confirmDialog('Clear the bot log?'))) return;
    $('#log').replaceChildren();
  });

  $('#update-close').addEventListener('click', () => {
    state.update = null;
    renderUpdate();
  });

  bridge.onConfigChanged((payload) => {
    state.config = payload;
    state.version = payload.version;
    renderBotConfig();
    renderAiConfig();
  });

  bridge.onAuthEvent((evt) => {
    if (evt.type === 'code') showAuthCode(evt);
    else if (evt.type === 'done') {
      closeAuth();
      toast(`Signed in as @${evt.info.login}`);
    } else if (evt.type === 'error') {
      if (state.authOpen) showAuthError(evt.error);
    }
  });

  bridge.onBotStatus((s) => {
    state.running = s.running;
    renderStatus();
  });

  bridge.onBotError((e) => {
    toast(e.message);
  });

  bridge.onLog(appendLog);

  bridge.onUpdate((u) => {
    if (u.type === 'none') return;
    state.update = u;
    renderUpdate();
  });
}

async function init() {
  wireEvents();
  const config = await bridge.getConfig();
  state.config = config;
  state.version = config.version;
  $('#version-badge').textContent = `v${config.version}`;
  renderStatus();
  renderBotConfig();
  renderAiConfig();
  bridge.checkUpdate();
}

document.addEventListener('DOMContentLoaded', init);
