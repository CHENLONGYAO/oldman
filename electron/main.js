'use strict';

const { app, BrowserWindow, dialog, shell } = require('electron');
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const path = require('path');
const net = require('net');

const DEFAULT_PORT = 8502;
const STREAMLIT_STARTUP_TIMEOUT_MS = 60000;
const POLL_INTERVAL_MS = 500;
const APP_TITLE = 'SmartRehab';

let streamlitProcess = null;
let mainWindow = null;
let streamlitPort = DEFAULT_PORT;

function getAppRoot() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'app');
  }
  return path.join(__dirname, '..');
}

function commandExists(command) {
  if (path.isAbsolute(command)) return fs.existsSync(command);
  const extensions = process.platform === 'win32'
    ? (process.env.PATHEXT || '.EXE;.CMD;.BAT;.COM').split(';')
    : [''];
  const paths = (process.env.PATH || '').split(path.delimiter);
  return paths.some((folder) => {
    if (!folder) return false;
    return extensions.some((ext) => fs.existsSync(path.join(folder, command + ext)));
  });
}

function firstExistingPython(appRoot) {
  const candidates = [
    { command: path.join(appRoot, '.venv311', 'Scripts', 'python.exe'), args: [] },
    { command: path.join(appRoot, '.venv', 'Scripts', 'python.exe'), args: [] },
    { command: path.join(appRoot, 'venv', 'Scripts', 'python.exe'), args: [] },
    { command: path.join(appRoot, '.venv311', 'bin', 'python3'), args: [] },
    { command: path.join(appRoot, '.venv', 'bin', 'python3'), args: [] },
    { command: 'py', args: ['-3.11'] },
    { command: 'python', args: [] },
    { command: 'python3', args: [] },
  ];

  return candidates.find((candidate) => commandExists(candidate.command));
}

function isPortOpen(port) {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    socket.setTimeout(300);
    socket.once('connect', () => {
      socket.destroy();
      resolve(true);
    });
    socket.once('error', () => {
      socket.destroy();
      resolve(false);
    });
    socket.once('timeout', () => {
      socket.destroy();
      resolve(false);
    });
    socket.connect(port, '127.0.0.1');
  });
}

async function findAvailablePort(startPort) {
  for (let port = startPort; port < startPort + 50; port += 1) {
    // eslint-disable-next-line no-await-in-loop
    if (!(await isPortOpen(port))) return port;
  }
  throw new Error('No available local port found for Streamlit.');
}

function checkHttpReady(port) {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${port}/_stcore/health`, (res) => {
      res.resume();
      resolve(res.statusCode >= 200 && res.statusCode < 500);
    });
    req.setTimeout(800, () => {
      req.destroy();
      resolve(false);
    });
    req.on('error', () => resolve(false));
  });
}

function waitForStreamlit(port, timeoutMs) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs;
    const poll = async () => {
      if (await checkHttpReady(port)) return resolve();
      if (Date.now() > deadline) {
        return reject(new Error('Streamlit startup timed out.'));
      }
      setTimeout(poll, POLL_INTERVAL_MS);
    };
    poll();
  });
}

function loadingHtml(message) {
  return `data:text/html;charset=utf-8,${encodeURIComponent(`
<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <title>${APP_TITLE}</title>
  <style>
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #1f2937;
      background: #f7fafc;
    }
    main {
      text-align: center;
      line-height: 1.7;
    }
    .spinner {
      width: 44px;
      height: 44px;
      margin: 0 auto 18px;
      border: 4px solid #dbeafe;
      border-top-color: #2563eb;
      border-radius: 50%;
      animation: spin 0.9s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <main>
    <div class="spinner"></div>
    <h1>${APP_TITLE}</h1>
    <p>${message}</p>
  </main>
</body>
</html>
`)}`;
}

function launchStreamlit(port) {
  const appRoot = getAppRoot();
  const appPy = path.join(appRoot, 'app.py');
  const python = firstExistingPython(appRoot);

  if (!python) {
    throw new Error('Python was not found. Install Python 3.11 or build the app with .venv311 included.');
  }

  const args = [
    ...python.args,
    '-m', 'streamlit', 'run', appPy,
    '--server.port', String(port),
    '--server.headless', 'true',
    '--server.runOnSave', 'false',
    '--browser.gatherUsageStats', 'false',
    '--client.toolbarMode', 'minimal',
  ];

  streamlitProcess = spawn(python.command, args, {
    cwd: appRoot,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: {
      ...process.env,
      PYTHONUNBUFFERED: '1',
      SMART_REHAB_DATA_DIR: path.join(app.getPath('userData'), 'user_data'),
      SMART_REHAB_TEMPLATE_DIR: path.join(app.getPath('userData'), 'templates_custom'),
    },
    windowsHide: true,
  });

  streamlitProcess.stdout.on('data', (d) => {
    console.log('[streamlit]', d.toString().trim());
  });
  streamlitProcess.stderr.on('data', (d) => {
    console.error('[streamlit]', d.toString().trim());
  });
  streamlitProcess.on('exit', (code) => {
    console.log(`[streamlit] exited with code ${code}`);
    streamlitProcess = null;
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.loadURL(loadingHtml('Background service stopped. Please reopen the app.'));
    }
  });
}

function createWindow() {
  const iconPath = path.join(__dirname, 'assets', 'icon.png');
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 700,
    title: APP_TITLE,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
    icon: fs.existsSync(iconPath) ? iconPath : undefined,
  });

  mainWindow.setMenuBarVisibility(false);

  mainWindow.webContents.session.setPermissionRequestHandler(
    (_webContents, permission, callback) => {
      callback(['media', 'camera', 'microphone'].includes(permission));
    },
  );

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith(`http://127.0.0.1:${streamlitPort}`)) {
      shell.openExternal(url);
    }
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(async () => {
  createWindow();
  mainWindow.loadURL(loadingHtml('Starting rehabilitation assessment service...'));

  try {
    streamlitPort = await findAvailablePort(DEFAULT_PORT);
    launchStreamlit(streamlitPort);
    await waitForStreamlit(streamlitPort, STREAMLIT_STARTUP_TIMEOUT_MS);
  } catch (err) {
    const message = err && err.message ? err.message : String(err);
    console.error(message);
    dialog.showErrorBox(APP_TITLE, `App failed to start:\n\n${message}`);
    mainWindow.loadURL(loadingHtml(`Startup failed: ${message}`));
    return;
  }

  mainWindow.loadURL(`http://127.0.0.1:${streamlitPort}`);
});

function stopStreamlit() {
  if (streamlitProcess) {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(streamlitProcess.pid), '/T', '/F'], {
        windowsHide: true,
      });
    } else {
      streamlitProcess.kill();
    }
    streamlitProcess = null;
  }
}

app.on('window-all-closed', () => {
  stopStreamlit();
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
    mainWindow.loadURL(`http://127.0.0.1:${streamlitPort}`);
  }
});

app.on('before-quit', () => {
  stopStreamlit();
});
