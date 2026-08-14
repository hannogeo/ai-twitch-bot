'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  getConfig: () => ipcRenderer.invoke('config:get'),
  saveBotConfig: (patch) => ipcRenderer.invoke('config:save-bot', patch),
  saveAiConfig: (patch) => ipcRenderer.invoke('config:save-ai', patch),
  setChatterContext: (patch) => ipcRenderer.invoke('config:set-chatter-context', patch),

  signIn: (accountKey) => ipcRenderer.invoke('auth:sign-in', accountKey),
  signOut: (accountKey) => ipcRenderer.invoke('auth:sign-out', accountKey),
  cancelSignIn: () => ipcRenderer.invoke('auth:cancel'),

  toggleBot: () => ipcRenderer.invoke('bot:toggle'),

  checkUpdate: () => ipcRenderer.invoke('update:check'),
  startUpdate: (url) => ipcRenderer.invoke('update:start', url),

  openExternal: (url) => ipcRenderer.invoke('app:open-external', url),
  copyText: (text) => ipcRenderer.invoke('app:copy-text', text),

  onConfigChanged: (cb) => ipcRenderer.on('config:changed', (_e, payload) => cb(payload)),
  onAuthEvent: (cb) => ipcRenderer.on('auth:event', (_e, payload) => cb(payload)),
  onBotStatus: (cb) => ipcRenderer.on('bot:status', (_e, payload) => cb(payload)),
  onBotError: (cb) => ipcRenderer.on('bot:error', (_e, payload) => cb(payload)),
  onLog: (cb) => ipcRenderer.on('log:append', (_e, payload) => cb(payload)),
  onUpdate: (cb) => ipcRenderer.on('update:event', (_e, payload) => cb(payload)),
});
