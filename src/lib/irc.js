'use strict';

const tls = require('tls');

class RateLimiter {
  constructor(maxCalls, period) {
    this.maxCalls = maxCalls;
    this.period = period;
    this.timestamps = [];
  }

  acquire() {
    const now = Date.now() / 1000;
    while (this.timestamps.length && now - this.timestamps[0] > this.period) {
      this.timestamps.shift();
    }
    if (this.timestamps.length < this.maxCalls) {
      this.timestamps.push(now);
      return 0;
    }
    const wait = this.period - (now - this.timestamps[0]);
    this.timestamps.push(now + wait);
    return wait;
  }
}

function _sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function parseMessage(raw) {
  let tags = {};
  let rest = raw;
  if (rest.startsWith('@')) {
    const idx = rest.indexOf(' ');
    if (idx >= 0) {
      for (const part of rest.slice(1, idx).split(';')) {
        const eq = part.indexOf('=');
        if (eq >= 0) tags[part.slice(0, eq)] = part.slice(eq + 1);
      }
      rest = rest.slice(idx + 1);
    }
  }
  const pm = rest.indexOf(' PRIVMSG ');
  if (pm < 0) return null;
  const prefix = rest.slice(0, pm);
  const trailing = rest.slice(pm + ' PRIVMSG '.length);
  const colIdx = prefix.lastIndexOf(':');
  const user = prefix.slice(colIdx + 1).split('!')[0];
  const sp = trailing.indexOf(' :');
  if (sp < 0) return null;
  const channel = trailing.slice(0, sp).split(' ')[0];
  const message = trailing.slice(sp + 2).trim();
  return { user, channel, message, tags };
}

class IRCBot {
  constructor(config, ai, logCallback) {
    this.config = config;
    this.ai = ai;
    this.logCallback = logCallback;
    this.sock = null;
    this.stopped = false;
    this.rateLimiter = new RateLimiter(19, 30);
    this.lastChannelSend = 0;
    this._buffer = '';
    this._queue = Promise.resolve();
  }

  _normalizeToken(token) {
    token = String(token || '').trim();
    return token.startsWith('oauth:') ? token : `oauth:${token}`;
  }

  _send(data) {
    if (!this.sock) return false;
    try {
      this.sock.write(data);
      return true;
    } catch (_e) {
      return false;
    }
  }

  async _rateLimitedSend(msg) {
    const wait = this.rateLimiter.acquire();
    if (wait > 0) await _sleep(wait * 1000);
    const now = Date.now() / 1000;
    const sinceLast = now - this.lastChannelSend;
    if (sinceLast < 1.1) await _sleep((1.1 - sinceLast) * 1000);
    this.lastChannelSend = Date.now() / 1000;
    return this._send(msg);
  }

  async stop() {
    this.stopped = true;
    const cfg = this.config;
    const sock = this.sock;
    if (!sock) return;
    if (cfg.DISCONNECT_MSG_ENABLED && !this._disconnectMsgSent) {
      this._disconnectMsgSent = true;
      try {
        const ok = await this._rateLimitedSend(`PRIVMSG #${cfg.CHANNEL} :${cfg.DISCONNECT_MSG}\r\n`);
        if (ok) this.logCallback(`BOT -> #${cfg.CHANNEL}: ${cfg.DISCONNECT_MSG}`);
      } catch (_e) {}
    }
    try {
      sock.end();
    } catch (_e) {}
  }

  async _handleLine(line) {
    if (!line) return;
    if (line.startsWith('PING')) {
      this._send('PONG :tmi.twitch.tv\r\n');
      return;
    }
    if (!line.includes('PRIVMSG')) return;

    const cfg = this.config;
    const parsed = parseMessage(line);
    if (!parsed || !parsed.user || !parsed.message) return;
    const { user, message, tags } = parsed;
    this.logCallback(`${user}: ${message}`);

    const msgLower = message.toLowerCase();
    const nickLower = String(cfg.NICK || '').toLowerCase();
    const parentUser = tags['reply-parent-user-login'];

    const tTag = cfg.TRIGGER_TAG !== false;
    const tCmd = cfg.TRIGGER_CMD !== false;
    const tRep = cfg.TRIGGER_REP !== false;
    const tOtherRep = cfg.TRIGGER_OTHER_REP !== false;

    const rawCmds = String(cfg.COMMANDS || '!ai, !aichat');
    const cmds = rawCmds
      .split(',')
      .map((c) => c.trim().toLowerCase())
      .filter(Boolean)
      .sort((a, b) => b.length - a.length);

    const isTag = tTag && nickLower && msgLower.includes(`@${nickLower}`);
    const isRep = tRep && parentUser && parentUser.toLowerCase() === nickLower;

    let isCmd = false;
    let matchedCmd = null;
    if (tCmd) {
      for (const c of cmds) {
        if (msgLower === c || msgLower.startsWith(`${c} `)) {
          isCmd = true;
          matchedCmd = c;
          break;
        }
      }
    }

    let canTrigger;
    if (parentUser && parentUser.toLowerCase() !== nickLower && !tOtherRep) {
      canTrigger = isCmd;
    } else {
      canTrigger = isTag || isCmd || isRep;
    }

    if (!canTrigger) return;

    let prompt = message.trim();
    if (matchedCmd) {
      prompt = msgLower.startsWith(`${matchedCmd} `)
        ? message.slice(matchedCmd.length).trim()
        : '';
    } else if (isTag && nickLower) {
      prompt = message.replace(new RegExp(`@${nickLower.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`, 'gi'), '').trim();
    }
    if (!prompt) prompt = 'Say hi!';

    let finalPrompt = prompt;
    if (parentUser) {
      const parentMsg = String(tags['reply-parent-msg-body'] || '').replace(/\\s/g, ' ');
      finalPrompt = `[Replying to @${parentUser}: "${parentMsg}"]\n\n${prompt}`;
    }

    if (this.stopped) return;
    const response = await this.ai.getAiResponse(finalPrompt, user);
    if (!response || this.stopped) return;

    const msgId = tags.id;
    let sent;
    if (msgId) {
      sent = await this._rateLimitedSend(`@reply-parent-msg-id=${msgId} PRIVMSG #${cfg.CHANNEL} :${response}\r\n`);
    } else {
      sent = await this._rateLimitedSend(`PRIVMSG #${cfg.CHANNEL} :@${user} ${response}\r\n`);
    }
    this.logCallback(sent ? `BOT -> ${user}: ${response}` : `BOT -> ${user}: ${response} (SEND FAILED)`);
  }

  run() {
    const cfg = this.config;
    return new Promise((resolve) => {
      if (!cfg.TOKEN || !cfg.NICK || !cfg.CHANNEL) {
        this.logCallback('Missing credentials in Bot Config.');
        resolve();
        return;
      }

      this.stopped = false;
      this._buffer = '';
      this._queue = Promise.resolve();

      this.sock = tls.connect(
        { host: 'irc.chat.twitch.tv', port: 6697, servername: 'irc.chat.twitch.tv' },
        () => {
          if (this.stopped) return;
          const token = this._normalizeToken(cfg.TOKEN);
          const nick = String(cfg.NICK).toLowerCase().trim();
          this._send(`PASS ${token}\r\n`);
          this._send(`NICK ${nick}\r\n`);
          this._send('CAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership\r\n');
          this._send(`JOIN #${cfg.CHANNEL}\r\n`);
          this.logCallback(`Connected to #${cfg.CHANNEL}`);
          if (cfg.CONNECT_MSG_ENABLED) {
            this._rateLimitedSend(`PRIVMSG #${cfg.CHANNEL} :${cfg.CONNECT_MSG}\r\n`).then((ok) => {
              if (ok) this.logCallback(`BOT -> #${cfg.CHANNEL}: ${cfg.CONNECT_MSG}`);
            }).catch(() => {});
          }
        }
      );

      this.sock.on('data', (chunk) => {
        this._buffer += chunk.toString('utf8');
        let nl;
        while ((nl = this._buffer.indexOf('\r\n')) >= 0) {
          const line = this._buffer.slice(0, nl);
          this._buffer = this._buffer.slice(nl + 2);
          this._queue = this._queue.then(() => this._handleLine(line)).catch(() => {});
        }
      });

      this.sock.on('error', (err) => {
        this.logCallback(`Connection Error: ${err.message}`);
      });

      this.sock.on('close', () => {
        this.sock = null;
        this.logCallback('Disconnected.');
        resolve();
      });
    });
  }
}

module.exports = { IRCBot, RateLimiter, parseMessage };
