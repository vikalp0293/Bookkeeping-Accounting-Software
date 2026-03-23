/**
 * Build Embedded Python for Windows
 *
 * Downloads the Python Windows embeddable package, enables pip (get-pip.py),
 * installs requirements, and outputs to resources/python-portable so the
 * Electron app can ship Python with no user install required.
 *
 * Run on Windows only (requires Python on build machine to run get-pip and pip install).
 * Usage: node scripts/build-embedded-python.js
 */

const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');
const { execSync } = require('child_process');

// Use Python 3.10 embed, 32-bit (win32) so COM works with 32-bit QuickBooks Desktop
const PYTHON_EMBED_VERSION = '3.10.11';
const PYTHON_EMBED_URL = `https://www.python.org/ftp/python/${PYTHON_EMBED_VERSION}/python-${PYTHON_EMBED_VERSION}-embed-win32.zip`;
const GET_PIP_URL = 'https://bootstrap.pypa.io/get-pip.py';

const projectRoot = path.join(__dirname, '..');
const resourcesDir = path.join(projectRoot, 'resources');
const pythonPortableDir = path.join(resourcesDir, 'python-portable');
const pythonDir = path.join(projectRoot, 'python');
const requirementsFile = path.join(pythonDir, 'requirements.txt');

function log(msg) {
  console.log(`[build-embedded-python] ${msg}`);
}

function downloadFile(url, destPath) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(destPath);
    const protocol = url.startsWith('https') ? https : http;
    protocol.get(url, { redirect: true }, (response) => {
      if (response.statusCode === 301 || response.statusCode === 302) {
        file.close();
        fs.unlinkSync(destPath);
        downloadFile(response.headers.location, destPath).then(resolve).catch(reject);
        return;
      }
      response.pipe(file);
      file.on('finish', () => {
        file.close();
        resolve();
      });
    }).on('error', (err) => {
      fs.unlink(destPath, () => {});
      reject(err);
    });
  });
}

function extractZip(zipPath, outDir) {
  // Use PowerShell Expand-Archive (built-in on Windows 5+)
  execSync(`powershell -Command "Expand-Archive -Path '${zipPath.replace(/'/g, "''")}' -DestinationPath '${outDir.replace(/'/g, "''")}' -Force"`, {
    stdio: 'inherit',
    shell: true
  });
}

function enableSiteInPth(portableDir) {
  // Find ._pth file (python310._pth for 3.10)
  const files = fs.readdirSync(portableDir);
  const pthFile = files.find(f => f.endsWith('._pth'));
  if (!pthFile) {
    throw new Error('No ._pth file found in embed package');
  }
  const pthPath = path.join(portableDir, pthFile);
  let content = fs.readFileSync(pthPath, 'utf-8');
  // Uncomment "import site" so site-packages is used
  content = content.replace(/# ?import site/g, 'import site');
  fs.writeFileSync(pthPath, content);
  log(`Updated ${pthFile} to enable site-packages`);
}

function runGetPip(portableDir) {
  const pythonExe = path.join(portableDir, 'python.exe');
  const getPipPath = path.join(portableDir, 'get-pip.py');
  execSync(`"${pythonExe}" "${getPipPath}"`, {
    stdio: 'inherit',
    shell: true,
    cwd: portableDir
  });
}

function runPipInstall(portableDir, requirementsPath) {
  const pythonExe = path.join(portableDir, 'python.exe');
  execSync(`"${pythonExe}" -m pip install --no-cache-dir -r "${requirementsPath}"`, {
    stdio: 'inherit',
    shell: true,
    cwd: portableDir
  });
}

// Zip filename for Mac build (downloaded and packaged; extracted on Windows at first run)
const PYTHON_EMBED_ZIP_BASENAME = 'python-embed-win32.zip';

async function main() {
  if (process.platform !== 'win32') {
    // Build on Mac/Linux: download the Windows 32-bit embed zip so the installer includes it.
    // On first run on Windows, the app will extract it and set up Python.
    log('Not Windows: downloading Windows 32-bit embed zip for installer (extracted on first run on Windows).');
    const zipDest = path.join(resourcesDir, PYTHON_EMBED_ZIP_BASENAME);
    if (!fs.existsSync(resourcesDir)) {
      fs.mkdirSync(resourcesDir, { recursive: true });
    }
    try {
      if (!fs.existsSync(zipDest)) {
        log(`Downloading ${PYTHON_EMBED_URL}...`);
        await downloadFile(PYTHON_EMBED_URL, zipDest);
        log(`Downloaded to ${zipDest}`);
      } else {
        log(`Using existing ${zipDest}`);
      }
      // Placeholder so extraResources "python-portable" exists; app will extract zip to userData on first run
      if (!fs.existsSync(pythonPortableDir)) {
        fs.mkdirSync(pythonPortableDir, { recursive: true });
        fs.writeFileSync(path.join(pythonPortableDir, '.extract-from-zip'), 'App extracts python-embed-win32.zip on first run on Windows.');
      }
      log('Installer will include the zip; app extracts on Windows first run.');
    } catch (err) {
      console.error('[build-embedded-python] Error:', err.message);
      process.exit(1);
    }
    process.exit(0);
  }

  if (!fs.existsSync(requirementsFile)) {
    log('requirements.txt not found; skipping.');
    process.exit(0);
  }

  log('Building embedded Python for Windows (32-bit for QuickBooks Desktop COM)...');
  log(`Python embed version: ${PYTHON_EMBED_VERSION} (win32)`);
  log(`Output directory: ${pythonPortableDir}`);

  const tempDir = path.join(projectRoot, 'temp-embed-build');
  const zipPath = path.join(tempDir, `python-${PYTHON_EMBED_VERSION}-embed-win32.zip`);
  const getPipPath = path.join(tempDir, 'get-pip.py');

  try {
    if (!fs.existsSync(tempDir)) {
      fs.mkdirSync(tempDir, { recursive: true });
    }

    // Download embed zip
    if (!fs.existsSync(zipPath)) {
      log(`Downloading ${PYTHON_EMBED_URL}...`);
      await downloadFile(PYTHON_EMBED_URL, zipPath);
      log('Downloaded embed zip.');
    } else {
      log('Using existing embed zip.');
    }

    // Download get-pip.py
    log(`Downloading get-pip.py...`);
    await downloadFile(GET_PIP_URL, getPipPath);
    log('Downloaded get-pip.py.');

    // Clean output and extract
    if (fs.existsSync(pythonPortableDir)) {
      fs.rmSync(pythonPortableDir, { recursive: true });
    }
    fs.mkdirSync(pythonPortableDir, { recursive: true });
    extractZip(zipPath, pythonPortableDir);
    log('Extracted embed package.');

    // Copy get-pip into portable dir so we can run it
    fs.copyFileSync(getPipPath, path.join(pythonPortableDir, 'get-pip.py'));

    // Enable site-packages in _pth
    enableSiteInPth(pythonPortableDir);

    // Install pip
    log('Installing pip into embedded Python...');
    runGetPip(pythonPortableDir);

    // Install requirements
    log('Installing requirements...');
    runPipInstall(pythonPortableDir, requirementsFile);

    log('Embedded Python build complete.');
    log(`Python is at: ${pythonPortableDir}`);
    // Also copy zip to resources so Mac-built installers can ship the zip (optional; used when building on Mac)
    const zipInResources = path.join(resourcesDir, PYTHON_EMBED_ZIP_BASENAME);
    if (!fs.existsSync(zipInResources)) {
      fs.copyFileSync(zipPath, zipInResources);
      log(`Copied zip to ${zipInResources}`);
    }
  } catch (err) {
    console.error('[build-embedded-python] Error:', err.message);
    process.exit(1);
  } finally {
    if (fs.existsSync(tempDir)) {
      fs.rmSync(tempDir, { recursive: true });
    }
  }
}

main();
