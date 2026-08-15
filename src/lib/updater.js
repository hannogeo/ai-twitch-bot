'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn, execFile } = require('child_process');
const { promisify } = require('util');
const execFileAsync = promisify(execFile);

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
  let writeError = null;
  out.on('error', (err) => {
    writeError = err;
  });
  const reader = resp.body.getReader();
  let downloaded = 0;
  const start = Date.now();
  let lastUpdate = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!out.write(Buffer.from(value))) {
        await new Promise((resolve) => out.once('drain', resolve));
      }
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
  } catch (e) {
    out.destroy();
    fs.rmSync(zipPath, { force: true });
    throw e;
  }
  await new Promise((resolve, reject) => {
    out.end((err) => {
      if (err) reject(err);
      else if (writeError) reject(writeError);
      else resolve();
    });
  });
  if (writeError) {
    fs.rmSync(zipPath, { force: true });
    throw writeError;
  }
  let size = 0;
  try {
    size = fs.statSync(zipPath).size;
  } catch (_e) {}
  if (size <= 0 || (total > 0 && size !== total)) {
    fs.rmSync(zipPath, { force: true });
    throw new Error(`Downloaded update is incomplete (${size}/${total} bytes).`);
  }
  return zipPath;
}

const UPDATE_TASK_NAME = 'AITwitchBotUpdate';

function futureTaskTime(minutesAhead) {
  const d = new Date(Date.now() + minutesAhead * 60000);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function writeUpdateBat(batPath, baseDir, exeName, source, tempDir, zipPath) {
  const waitFile = path.join(baseDir, 'update_wait.txt');
  const vbsPath = path.join(baseDir, 'run-update.vbs');
  const exePath = path.join(baseDir, exeName);
  const lines = [
    '@echo off',
    'chcp 65001 >nul',
    'set /a tries=0',
    ':waitloop',
    'set /a tries+=1',
    `tasklist /FI "IMAGENAME eq ${exeName}" /FO CSV 2>nul > "${waitFile}"`,
    `find /I "${exeName}" "${waitFile}" >nul`,
    'if not errorlevel 1 (',
    '    if %tries% GEQ 120 goto proceed',
    '    ping -n 2 127.0.0.1 >nul',
    '    goto waitloop',
    ')',
    ':proceed',
    `xcopy "${source}\\*" "${baseDir}\\" /E /Y /Q`,
    'echo Updating files...',
    `rmdir /S /Q "${tempDir}" 2>nul`,
    `del "${zipPath}" 2>nul`,
    `del "${waitFile}" 2>nul`,
    `schtasks /Delete /F /TN "${UPDATE_TASK_NAME}"`,
    `start "" "${exePath}"`,
    `del "${vbsPath}" 2>nul`,
    'del "%~f0"',
  ].join('\r\n');
  fs.writeFileSync(batPath, lines);
}

function writeUpdateVbs(vbsPath, batPath) {
  const vbs = [
    'Set ws = CreateObject("WScript.Shell")',
    `ws.Run "cmd.exe /c ""${batPath}""", 0, True`,
  ].join('\r\n');
  fs.writeFileSync(vbsPath, vbs);
}

async function scheduleUpdateTask(vbsPath) {
  const wscript = path.join(process.env.WINDIR || 'C:\\Windows', 'System32', 'wscript.exe');

  const registerViaPowerShell = async () => {
    const ps = `Register-ScheduledTask -Force -TaskName ${UPDATE_TASK_NAME} -Action (New-ScheduledTaskAction -Execute '${wscript}' -Argument '"${vbsPath}"') -Trigger (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1)) -Description 'AI Twitch Bot updater' | Out-Null`;
    await execFileAsync('powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps], { windowsHide: true });
    await execFileAsync('powershell', ['-NoProfile', '-Command', `Start-ScheduledTask -TaskName ${UPDATE_TASK_NAME}`], { windowsHide: true });
  };

  const registerViaSchtasks = async () => {
    const tr = `"${wscript}" "${vbsPath}"`;
    const st = futureTaskTime(2);
    await execFileAsync('schtasks', ['/Create', '/F', '/TN', UPDATE_TASK_NAME, '/TR', tr, '/SC', 'ONCE', '/ST', st], { windowsHide: true });
    await execFileAsync('schtasks', ['/Run', '/TN', UPDATE_TASK_NAME], { windowsHide: true });
  };

  try {
    await registerViaPowerShell();
  } catch (err) {
    try {
      await registerViaSchtasks();
    } catch (err2) {
      throw new Error(`Could not schedule updater (${err.message}; ${err2.message})`);
    }
  }
}

async function applyUpdate(zipPath, baseDir, exeName) {
  let zipSize = 0;
  try {
    zipSize = fs.statSync(zipPath).size;
  } catch (_e) {}
  if (zipSize <= 0) {
    throw new Error(`Update archive not found or empty: ${zipPath}`);
  }
  const tempDir = path.join(baseDir, 'update_temp');
  fs.rmSync(tempDir, { recursive: true, force: true });
  fs.mkdirSync(tempDir, { recursive: true });
  try {
    await execFileAsync('tar', ['-xf', zipPath, '-C', tempDir], { windowsHide: true });
  } catch (err) {
    throw new Error(`Extraction failed: ${err.message}`);
  }

  let source = path.join(tempDir, 'AITwitchBot');
  if (!fs.existsSync(source)) source = tempDir;

  const batPath = path.join(baseDir, 'update.bat');
  const vbsPath = path.join(baseDir, 'run-update.vbs');
  writeUpdateBat(batPath, baseDir, exeName, source, tempDir, zipPath);
  writeUpdateVbs(vbsPath, batPath);

  try {
    await scheduleUpdateTask(vbsPath);
  } catch (err) {
    spawn(batPath, [], { shell: true, detached: true, stdio: 'ignore', windowsHide: true }).unref();
  }
}

async function cleanupUpdateArtifacts(baseDir) {
  for (const name of ['update_temp', 'update.zip', 'update.bat', 'update_wait.txt', 'run-update.vbs']) {
    try {
      fs.rmSync(path.join(baseDir, name), { recursive: true, force: true });
    } catch (_e) {}
  }
  try {
    await execFileAsync('schtasks', ['/Delete', '/F', '/TN', UPDATE_TASK_NAME], { windowsHide: true });
  } catch (_e) {}
}

module.exports = {
  parseSemver,
  compareSemver,
  getLocalVersion,
  checkForUpdate,
  downloadUpdate,
  applyUpdate,
  cleanupUpdateArtifacts,
  writeUpdateBat,
  writeUpdateVbs,
  scheduleUpdateTask,
};
