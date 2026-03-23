/**
 * Simple script to create a placeholder icon
 * Run: node create_icon.js
 */

const fs = require('fs');
const path = require('path');

// Create a minimal valid PNG (1x1 transparent pixel)
// This is a base64 encoded minimal PNG
const minimalPNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==',
  'base64'
);

// For a better icon, we'd need a graphics library
// For now, create a simple placeholder that electron-builder can work with
const iconPath = path.join(__dirname, 'icon.png');

try {
  fs.writeFileSync(iconPath, minimalPNG);
  console.log('✓ Created placeholder icon.png');
  console.log('⚠️  Note: This is a minimal placeholder. For production, replace with a proper 1024x1024 PNG icon.');
} catch (error) {
  console.error('Failed to create icon:', error);
  process.exit(1);
}

