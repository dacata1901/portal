const { spawn, spawnSync } = require('node:child_process');
const { existsSync } = require('node:fs');
const { homedir } = require('node:os');
const { join } = require('node:path');
const root = join(__dirname, '..');
const bundled = join(homedir(), '.cache', 'codex-runtimes', 'codex-primary-runtime', 'dependencies', 'python', 'python.exe');
const candidates = [process.env.PYTHON && [process.env.PYTHON], ['py', '-3'], ['python3'], ['python'], existsSync(bundled) && [bundled]].filter(Boolean);
const python = candidates.find(([cmd, ...args]) => {
  const result = spawnSync(cmd, [...args, '-c', 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'], { stdio: 'ignore', windowsHide: true, timeout: 3000 });
  return !result.error && result.status === 0;
});
if (!python) { console.error('Cần Python 3.10 trở lên. Cài Python hoặc đặt biến PYTHON trỏ tới python.exe.'); process.exitCode = 1; }
else {
  const [cmd, ...args] = python;
  const child = spawn(cmd, [...args, 'server.py'], { cwd: root, stdio: 'inherit', windowsHide: true, env: process.env });
  child.on('error', err => { console.error('Không khởi động được:', err?.message || String(err)); process.exitCode = 1; });
  child.on('exit', (code, signal) => { process.exitCode = signal === 'SIGINT' ? 0 : code ?? 1; });
  process.once('SIGINT', () => child.kill('SIGINT'));
  process.once('SIGTERM', () => child.kill('SIGTERM'));
}
