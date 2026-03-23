const fs = require('fs');
const path = require('path');

const frontendDist = path.join(__dirname, '../../frontend/dist');
const desktopFrontend = path.join(__dirname, '../frontend/dist');

if (!fs.existsSync(frontendDist)) {
  console.error('Frontend dist directory not found. Run: cd ../frontend && npm run build');
  process.exit(1);
}

if (fs.existsSync(desktopFrontend)) {
  fs.rmSync(desktopFrontend, { recursive: true, force: true });
}

fs.cpSync(frontendDist, desktopFrontend, { recursive: true });
console.log('Frontend copied successfully');


