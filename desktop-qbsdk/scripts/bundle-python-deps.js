/**
 * Download Windows 32-bit Python 3.10 wheels for bundled offline install.
 * Run on Mac/Linux before building the Windows installer so users don't need
 * Visual C++ Build Tools (pip would otherwise build psutil from source).
 *
 * Requires: pip (python3 -m pip)
 */

const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const projectRoot = path.resolve(__dirname, '..');
const requirementsPath = path.join(projectRoot, 'python', 'requirements.txt');
const wheelsDir = path.join(projectRoot, 'python', 'dependencies', 'wheels');

if (!fs.existsSync(requirementsPath)) {
  console.error('requirements.txt not found at', requirementsPath);
  process.exit(1);
}

if (!fs.existsSync(path.dirname(wheelsDir))) {
  fs.mkdirSync(path.dirname(wheelsDir), { recursive: true });
}
if (!fs.existsSync(wheelsDir)) {
  fs.mkdirSync(wheelsDir, { recursive: true });
}

// Build a requirements string for win32 that includes pywinauto (normally skipped by sys_platform marker on Mac)
// and comtypes (pywinauto's Windows-only dependency, not always pulled by pip download from Mac)
const baseReqs = fs.readFileSync(requirementsPath, 'utf8')
  .split('\n')
  .map(line => line.trim())
  .filter(Boolean);
const winReqs = baseReqs.map(line => line.replace(/;\s*sys_platform\s*==\s*['"]win32['"]\s*$/, ''));
if (!winReqs.some(r => r.toLowerCase().startsWith('comtypes'))) {
  winReqs.push('comtypes');
}
const winReqsPath = path.join(projectRoot, 'python', 'dependencies', 'requirements-win32.txt');
fs.mkdirSync(path.dirname(winReqsPath), { recursive: true });
fs.writeFileSync(winReqsPath, winReqs.join('\n') + '\n', 'utf8');

// Target: Windows 32-bit, Python 3.10 (matches embedded Python used on Windows)
const cmd = [
  'python3', '-m', 'pip', 'download',
  '--platform', 'win32',
  '--python-version', '310',
  '--only-binary=:all:',
  '--dest', wheelsDir,
  '--requirement', winReqsPath
].map(arg => arg.includes(' ') ? `"${arg}"` : arg).join(' ');

console.log('Downloading Windows 32-bit Python 3.10 wheels...');
console.log('Target:', wheelsDir);

try {
  execSync(cmd, {
    cwd: projectRoot,
    stdio: 'inherit'
  });
  const files = fs.readdirSync(wheelsDir).filter(f => f.endsWith('.whl'));
  console.log('Downloaded', files.length, 'wheel(s).');
  try { fs.unlinkSync(winReqsPath); } catch (_) {}
} catch (err) {
  try { fs.unlinkSync(winReqsPath); } catch (_) {}
  console.error('pip download failed:', err.message);
  process.exit(1);
}
