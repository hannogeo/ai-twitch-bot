'use strict';

const path = require('path');
const { app, BrowserWindow, ipcMain } = require('electron');

const { makeConfig } = require('./lib/config');
const {
  AuthError,
  startDeviceFlow,
  pollForToken,
  getUserInfo,
  refreshStoredTokens,
  getEffectiveSettings,
} = require('./lib/twitch-auth');
const { AIModule } = require('./lib/ai');
const { IRCBot } = require('./lib/irc');
const { getLocalVersion, checkForUpdate, downloadUpdate, applyUpdate } = require('./lib/updater');

const BASE_DIR = app.isPackaged ? path.dirname(process.execPath) : path.join(__dirname, '.');
const VERSION = getLocalVersion(BASE_DIR);

const config = makeConfig(BASE_DIR);
const bot = config.bot;
const ai = config.ai;
const aiModule = new AIModule(ai);

let win = null;
let botState = { running: false, irc: null };
let activeAuth = null;

function send(channel, payload) {
  if (win && !win.isDestroyed()) {
    win.webContents.send(channel, payload);
  }
}

function log(line) {
  send('log:append', { text: String(line) });
}

function sendConfig() {
  send('config:changed', { bot: bot.data, ai: ai.data, version: VERSION });
}

// ── Bot control ──────────────────────────────────────────────────────────

async function toggleBot() {
  if (botState.running) {
    if (botState.irc) botState.irc.stop();
    botState.running = false;
    botState.irc = null;
    send('bot:status', { running: false });
    return { running: false };
  }

  try {
    await refreshStoredTokens(bot);
  } catch (_e) {}

  const eff = getEffectiveSettings(bot);
  if (!eff.TOKEN || !eff.NICK || !eff.CHANNEL) {
    send('bot:error', { message: 'Missing credentials. Set up Bot Config first.' });
    return { running: false, error: 'Missing credentials. Set up Bot Config first.' };
  }

  botState.running = true;
  send('bot:status', { running: true });

  const merged = { ...bot.data, ...eff };
  const irc = new IRCBot(merged, aiModule, log);
  botState.irc = irc;

  irc.run().then(() => {
    if (botState.running) {
      botState.running = false;
      botState.irc = null;
      send('bot:status', { running: false });
    }
  });

  return { running: true };
}

// ── Auth ─────────────────────────────────────────────────────────────────

function startSignIn(accountKey) {
  if (activeAuth) {
    activeAuth.cancelled = true;
  }
  activeAuth = { cancelled: false };

  (async () => {
    try {
      const flow = await startDeviceFlow();
      send('auth:event', {
        type: 'code',
        user_code: flow.user_code,
        verification_uri: flow.verification_uri || 'https://www.twitch.tv/activate',
      });
      const tokens = await pollForToken(flow.device_code, flow.interval, () => activeAuth && activeAuth.cancelled);
      let info = null;
      try {
        info = await getUserInfo(tokens.access_token);
      } catch (_e) {
        info = null;
      }
      if (!info) {
        throw new AuthError('Could not fetch account info.');
      }
      const auth = { ...(bot.get('TWITCH_AUTH') || {}) };
      auth[accountKey] = {
        login: info.login,
        display_name: info.display_name,
        access_token: tokens.access_token,
        refresh_token: tokens.refresh_token,
      };
      bot.set('TWITCH_AUTH', auth);
      bot.save();
      activeAuth = null;
      send('auth:event', { type: 'done', account: accountKey, info });
      sendConfig();
    } catch (e) {
      if (activeAuth && !activeAuth.cancelled) {
        send('auth:event', { type: 'error', error: e.message || 'Sign-in failed.' });
      }
      activeAuth = null;
    }
  })();
}

function signOut(accountKey) {
  const auth = { ...(bot.get('TWITCH_AUTH') || {}) };
  delete auth[accountKey];
  bot.set('TWITCH_AUTH', auth);
  bot.save();
  sendConfig();
  return { ok: true };
}

// ── Update ───────────────────────────────────────────────────────────────

async function checkUpdate() {
  const update = await checkForUpdate(BASE_DIR);
  send('update:event', update ? { type: 'available', version: update.version, url: update.url } : { type: 'none' });
}

async function startUpdate(url) {
  if (!app.isPackaged) {
    send('update:event', { type: 'error', error: 'Updates only work in packaged builds.' });
    return;
  }
  try {
    const zipPath = await downloadUpdate(url, BASE_DIR, (percent, kbps, remaining) => {
      send('update:event', { type: 'progress', percent, kbps, remaining });
    });
    send('update:event', { type: 'installing' });
    const exeName = path.basename(process.execPath);
    await applyUpdate(zipPath, BASE_DIR, exeName);
    setTimeout(() => app.quit(), 500);
  } catch (e) {
    send('update:event', { type: 'error', error: e.message || 'Update failed.' });
  }
}

// ── Window ───────────────────────────────────────────────────────────────

function createWindow() {
  win = new BrowserWindow({
    width: 900,
    height: 700,
    minWidth: 620,
    minHeight: 480,
    title: 'AI Twitch Bot',
    backgroundColor: '#121214',
    icon: path.join(BASE_DIR, 'assets', 'app-icon.ico'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.setMenuBarVisibility(false);
  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  win.on('closed', () => {
    win = null;
  });
}

// ── IPC ──────────────────────────────────────────────────────────────────

ipcMain.handle('config:get', () => ({ bot: bot.data, ai: ai.data, version: VERSION }));

ipcMain.handle('config:save-bot', (_e, patch) => {
  if (patch && typeof patch === 'object') {
    for (const key of ['CONNECT_MSG_ENABLED', 'DISCONNECT_MSG_ENABLED', 'TRIGGER_TAG', 'TRIGGER_CMD', 'TRIGGER_REP', 'TRIGGER_OTHER_REP', 'COMMANDS']) {
      if (key in patch) bot.set(key, patch[key]);
    }
    bot.save();
  }
  return { ok: true };
});

ipcMain.handle('config:save-ai', (_e, patch) => {
  if (patch && typeof patch === 'object') {
    if ('api_key' in patch) ai.set('api_key', patch.api_key);
    if ('system_instruction' in patch) ai.set('system_instruction', patch.system_instruction);
    ai.save();
    aiModule._initClient();
  }
  return { ok: true };
});

ipcMain.handle('config:set-chatter-context', (_e, patch) => {
  if (patch && typeof patch === 'object') {
    ai.set('chatter_context', patch);
    ai.save();
  }
  return { ok: true };
});

ipcMain.handle('auth:sign-in', (_e, accountKey) => {
  startSignIn(accountKey);
  return { ok: true };
});

ipcMain.handle('auth:sign-out', (_e, accountKey) => signOut(accountKey));

ipcMain.handle('auth:cancel', () => {
  if (activeAuth) activeAuth.cancelled = true;
  return { ok: true };
});

ipcMain.handle('bot:toggle', () => toggleBot());

ipcMain.handle('update:check', () => checkUpdate());

ipcMain.handle('update:start', (_e, url) => startUpdate(url));

ipcMain.handle('app:open-external', (_e, url) => {
  const { shell } = require('electron');
  shell.openExternal(url);
  return { ok: true };
});

ipcMain.handle('app:copy-text', (_e, text) => {
  const { clipboard } = require('electron');
  clipboard.writeText(String(text || ''));
  return { ok: true };
});

// ── Lifecycle ────────────────────────────────────────────────────────────

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });

  setTimeout(() => checkUpdate(), 3000);

  const eff = getEffectiveSettings(bot);
  if (eff.TOKEN) {
    setTimeout(() => {
      toggleBot();
    }, 1500);
  }
});

app.on('window-all-closed', () => {
  if (botState.irc) botState.irc.stop();
  app.quit();
});
