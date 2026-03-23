const fs = require('fs');
const path = require('path');

const src = path.join(__dirname, '../../frontend/dist');
const dest = path.join(__dirname, '../frontend/dist');

console.log(`Copying frontend from: ${src}`);
console.log(`To: ${dest}`);

if (!fs.existsSync(src)) {
  console.error(`Error: Frontend dist not found at ${src}`);
  console.error('Please build the frontend first: cd ../frontend && npm run build');
  process.exit(1);
}

// Remove destination if it exists
if (fs.existsSync(dest)) {
  console.log('Removing existing frontend/dist...');
  fs.rmSync(dest, { recursive: true, force: true });
}

// Create parent directory
const destParent = path.dirname(dest);
if (!fs.existsSync(destParent)) {
  fs.mkdirSync(destParent, { recursive: true });
}

// Copy files using Node.js fs for cross-platform compatibility
console.log('Copying files...');
try {
  // Recursive copy function
  function copyRecursiveSync(src, dest) {
    const exists = fs.existsSync(src);
    const stats = exists && fs.statSync(src);
    const isDirectory = exists && stats.isDirectory();
    
    if (isDirectory) {
      if (!fs.existsSync(dest)) {
        fs.mkdirSync(dest, { recursive: true });
      }
      fs.readdirSync(src).forEach(childItemName => {
        copyRecursiveSync(
          path.join(src, childItemName),
          path.join(dest, childItemName)
        );
      });
    } else {
      fs.copyFileSync(src, dest);
    }
  }
  
  copyRecursiveSync(src, dest);
  console.log('✓ Frontend copied successfully to desktop/frontend/dist');
} catch (error) {
  console.error('Error copying frontend:', error.message);
  console.error(error.stack);
  process.exit(1);
}

