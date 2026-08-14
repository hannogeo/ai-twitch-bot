'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

const GITHUB_REPO = 'hannogeo/ai-twitch-bot';

function parseSemver(version) {
  const parts = String(version || '').trim().replace(/^v/, '').split('.');
  const major = parts[0] && /^\d+$/.test(parts[0]) ? parseInt(parts[0], 10) : 0;
  const minor = parts[1] && /^\d+$/.test(parts[1]) ? parseInt(parts[1], 10) : 0;
  const patch = parts[2] && /^\d+$/.test(parts[2]) ? parseInt(parts[2], 10) : 0;
  return { major, minor, patch };
}

function compareSemver(a, b) {
  if (a.major !== b.major) return a.major - b.major;
  if (a.minor !== b.minor) return a.minor - b.minor;
  return a.patch - b.patch;
}

function getLocalVersion(baseDir) {
  try {
    const data = JSON.parse(fs.readFileSync(path.join(baseDir, 'version.json'), 'utf8'));
    return data.version || '0.0.0';
  } catch (_e) {
    return '0.0.0';
  }
}

async function checkForUpdate(baseDir) {
  try {
    const resp = await fetch(`https://api.github.com/repos/${GITHUB_REPO}/releases/latest`, { timeout: 5000 });
    if (resp.status !== 200) return null;
    const data = await resp.json();
    const latestTag = data.tag_name || '';
    const localVer = getLocalVersion(baseDir);
    if (compareSemver(parseSemver(latestTag), parseSemver(localVer)) <= 0) return null;
    const assets = data.assets || [];
    const zipAsset = assets.find((a) => a.name.endsWith('.zip') && !a.name.toLowerCase().includes('setup'));
    if (!zipAsset) return null;
    return { version: latestTag, url: zipAsset.browser_download_url };
  } catch (_e) {
    return null;
  }
}

async function downloadUpdate(url, baseDir, onProgress) {
  const zipPath = path.join(baseDir, 'update.zip');
  const resp = await fetch(url);
  if (!resp.ok || !resp.body) {
    throw new Error(`Download failed (HTTP ${resp.status}).`);
  }
  const total = parseInt(resp.headers.get('content-length') || '0', 10);
  const out = fs.createWriteStream(zipPath);
  const reader = resp.body.getReader();
  let downloaded = 0;
  const start = Date.now();
  let lastUpdate = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    out.write(Buffer.from(value));
    downloaded += value.length;
    const now = Date.now();
    if (onProgress && total && now - lastUpdate > 100) {
      const elapsed = (now - start) / 1000;
      const speed = downloaded / elapsed;
      const remaining = speed > 0 ? (total - downloaded) / speed : 0;
      onProgress(downloaded / total, speed / 1024, remaining);
      lastUpdate = now;
    }
  }
  await new Promise((resolve, reject) => {
    out.end((err) => (err ? reject(err) : resolve()));
  });
  return zipPath;
}

async function applyUpdate(zipPath, baseDir, exeName) {
  const extractZip = require('extract-zip');
  const tempDir = path.join(baseDir, 'update_temp');
  fs.rmSync(tempDir, { recursive: true, force: true });
  fs.mkdirSync(tempDir, { recursive: true });
  await extractZip(zipPath, { dir: tempDir });

  let source = path.join(tempDir, 'AITwitchBot');
  if (!fs.existsSync(source)) source = tempDir;

  const batPath = path.join(baseDir, 'update.bat');
  const batContent = [
    '@echo off',
    'chcp 65001 >nul',
    'echo Waiting for app to close...',
    ':waitloop',
    `tasklist /FI "IMAGENAME eq ${exeName}" 2>nul | find /I "${exeName}" >nul`,
    'if not errorlevel 1 (',
    '    timeout /t 1 /nobreak >nul',
    '    goto waitloop',
    ')',
    'echo Updating files...',
    `xcopy "${source}\\*" "${baseDir}\\" /E /Y /Q`,
    'echo Cleaning up...',
    `rmdir /S /Q "${tempDir}" 2>nul`,
    `del "${zipPath}" 2>nul`,
    `start "" "${path.join(baseDir, exeName)}"`,
    'del "%~f0"',
  ].join('\r\n');
  fs.writeFileSync(batPath, batContent);

  spawn(batPath, [], {
    shell: true,
    detached: true,
    stdio: 'ignore',
    windowsHide: true,
  }).unref();
}

module.exports = { parseSemver, compareSemver, getLocalVersion, checkForUpdate, downloadUpdate, applyUpdate };
