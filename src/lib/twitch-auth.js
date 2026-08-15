'use strict';

const TWITCH_CLIENT_ID = '8b08hy2m68pr26ax4xzowei5ogwaxn';
const SCOPES = 'chat:read chat:edit';

const DEVICE_URL = 'https://id.twitch.tv/oauth2/device';
const TOKEN_URL = 'https://id.twitch.tv/oauth2/token';
const USERS_URL = 'https://api.twitch.tv/helix/users';

class AuthError extends Error {}

function _form(body) {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams(body).toString(),
  };
}

function _sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function startDeviceFlow() {
  const resp = await fetch(DEVICE_URL, _form({ client_id: TWITCH_CLIENT_ID, scopes: SCOPES }));
  if (resp.status !== 200) {
    throw new AuthError(`Could not start sign-in (HTTP ${resp.status}).`);
  }
  return resp.json();
}

async function pollForToken(deviceCode, interval, cancelCheck) {
  while (!(cancelCheck && cancelCheck())) {
    await _sleep((interval || 5) * 1000);
    let resp;
    try {
      resp = await fetch(TOKEN_URL, _form({
        client_id: TWITCH_CLIENT_ID,
        device_code: deviceCode,
        grant_type: 'urn:ietf:params:oauth:grant-type:device_code',
      }));
    } catch (e) {
      throw new AuthError(`Network error: ${e.message}`);
    }
    const data = await resp.json();
    if (resp.status === 200 && data.access_token) {
      return data;
    }
    const msg = String(data.message || '').toLowerCase();
    if (msg === 'authorization_pending') continue;
    if (msg === 'slow_down') {
      interval = (interval || 5) + 5;
      continue;
    }
    if (msg === 'access_denied') {
      throw new AuthError('Sign-in was denied or cancelled on Twitch.');
    }
    if (msg.includes('expired') || msg.includes('invalid')) {
      throw new AuthError('The sign-in code expired. Please try again.');
    }
    throw new AuthError(`Sign-in failed: ${data.message || resp.status}`);
  }
  throw new AuthError('Sign-in cancelled.');
}

async function refreshAccessToken(refreshToken) {
  const resp = await fetch(TOKEN_URL, _form({
    client_id: TWITCH_CLIENT_ID,
    grant_type: 'refresh_token',
    refresh_token: refreshToken,
  }));
  const data = await resp.json();
  if (resp.status === 200 && data.access_token) {
    return data;
  }
  return null;
}

async function getUserInfo(accessToken) {
  const resp = await fetch(USERS_URL, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Client-Id': TWITCH_CLIENT_ID,
    },
  });
  if (resp.status === 200) {
    const users = (await resp.json()).data || [];
    if (users.length) {
      const u = users[0];
      const login = (u.login || '').toLowerCase();
      return { login, display_name: u.display_name || login };
    }
  }
  return null;
}

function _accountToken(entry) {
  const token = (entry || {}).access_token || '';
  return token ? `oauth:${token}` : '';
}

async function refreshStoredTokens(bot) {
  const auth = bot.get('TWITCH_AUTH') || {};
  let changed = false;
  for (const key of ['streamer', 'bot']) {
    const entry = auth[key] || {};
    if (!entry.refresh_token) continue;
    let refreshed = null;
    try {
      refreshed = await refreshAccessToken(entry.refresh_token);
    } catch (_e) {
      refreshed = null;
    }
    if (refreshed && refreshed.access_token) {
      entry.access_token = refreshed.access_token;
      if (refreshed.refresh_token) entry.refresh_token = refreshed.refresh_token;
      changed = true;
    }
  }
  if (changed) {
    bot.set('TWITCH_AUTH', auth);
    bot.save();
  }
  return changed;
}

function getEffectiveSettings(bot) {
  const auth = bot.get('TWITCH_AUTH') || {};
  const streamer = auth.streamer || {};
  const botAccount = auth.bot || {};

  let nick = '';
  let token = '';
  if (botAccount.login) {
    nick = botAccount.login;
    token = _accountToken(botAccount);
  } else if (streamer.login) {
    nick = streamer.login;
    token = _accountToken(streamer);
  }

  const channel = (streamer.login || '').toLowerCase();

  return {
    CHANNEL: channel,
    NICK: nick.trim().toLowerCase(),
    TOKEN: token.trim(),
  };
}

module.exports = {
  TWITCH_CLIENT_ID,
  AuthError,
  startDeviceFlow,
  pollForToken,
  refreshAccessToken,
  getUserInfo,
  refreshStoredTokens,
  getEffectiveSettings,
};
