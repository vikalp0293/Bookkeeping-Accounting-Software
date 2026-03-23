#!/usr/bin/env node

/**
 * Environment variable validation script for build process
 * Ensures required environment variables are set before building
 */

const requiredEnvVars = [
  'VITE_API_BASE_URL'
];

const optionalEnvVars = [
  'VITE_DEV_PORT',
  'VITE_API_PROXY_TARGET'
];

function checkEnvVars() {
  const missing = [];
  const warnings = [];

  // Check required variables
  requiredEnvVars.forEach(varName => {
    if (!process.env[varName]) {
      missing.push(varName);
    }
  });

  // Check optional variables (warn if missing)
  optionalEnvVars.forEach(varName => {
    if (!process.env[varName]) {
      warnings.push(varName);
    }
  });

  // Report results
  if (missing.length > 0) {
    console.error('\n❌ ERROR: Missing required environment variables:\n');
    missing.forEach(varName => {
      console.error(`   - ${varName}`);
    });
    console.error('\n💡 Tip: Create a .env file or set these variables before building.');
    console.error('   See .env.example for reference.\n');
    process.exit(1);
  }

  if (warnings.length > 0) {
    console.warn('\n⚠️  WARNING: Optional environment variables not set:\n');
    warnings.forEach(varName => {
      console.warn(`   - ${varName} (will use default value)`);
    });
    console.warn('');
  }

  if (missing.length === 0) {
    console.log('✅ All required environment variables are set.\n');
  }
}

// Run the check
checkEnvVars();

