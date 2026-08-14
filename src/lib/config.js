'use strict';

const fs = require('fs');
const path = require('path');

const BOT_DEFAULTS = {
  CONNECT_MSG_ENABLED: true,
  CONNECT_MSG: '/me is now connected...',
  DISCONNECT_MSG_ENABLED: true,
  DISCONNECT_MSG: '/me disconnected!',
  TRIGGER_TAG: true,
  TRIGGER_CMD: true,
  TRIGGER_REP: true,
  TRIGGER_OTHER_REP: true,
  COMMANDS: '!ai, !aichat',
  TWITCH_AUTH: { streamer: {}, bot: {} },
};

const AI_DEFAULTS = {
  api_key: '',
  system_instruction: 'You are a helpful AI Twitch bot.',
  chatter_context: {},
};

class JsonConfig {
  constructor(filePath, defaults) {
    this.filePath = filePath;
    this.data = JSON.parse(JSON.stringify(defaults));
    this.load();
  }

  load() {
    try {
      const raw = JSON.parse(fs.readFileSync(this.filePath, 'utf8'));
      this.data = { ...this.data, ...raw };
    } catch (_e) {
      // missing or invalid file: keep defaults
    }
  }

  save() {
    fs.mkdirSync(path.dirname(this.filePath), { recursive: true });
    fs.writeFileSync(this.filePath, JSON.stringify(this.data, null, 4));
  }

  get(key, fallback) {
    const value = this.data[key];
    return value !== undefined ? value : fallback !== undefined ? fallback : '';
  }

  set(key, value) {
    this.data[key] = value;
  }
}

function makeConfig(baseDir) {
  const dataDir = path.join(baseDir, 'data');
  const bot = new JsonConfig(path.join(dataDir, 'bot_config.json'), BOT_DEFAULTS);
  const ai = new JsonConfig(path.join(dataDir, 'ai_config.json'), AI_DEFAULTS);
  return { bot, ai, dataDir };
}

module.exports = { JsonConfig, makeConfig, BOT_DEFAULTS, AI_DEFAULTS };
