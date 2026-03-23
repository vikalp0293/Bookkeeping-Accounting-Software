import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current working directory.
  const env = loadEnv(mode, process.cwd(), '')

  return {
    base: './', // Use relative paths for Electron compatibility
    plugins: [react()],
    server: {
      host: true, // Listen on all network interfaces
      port: parseInt(env.VITE_DEV_PORT) || 5209,
      allowedHosts: [
        'dev-sync.kylientlabs.com',
        'localhost',
        '.kylientlabs.com'
      ],
      proxy: {
        '/api': {
          target: env.VITE_API_PROXY_TARGET || 'http://localhost:5208',
          changeOrigin: true,
          secure: false,
          rewrite: (path) => path
        }
      }
    },
    // Ensure environment variables are available at build time
    define: {
      'import.meta.env.VITE_API_BASE_URL': JSON.stringify(env.VITE_API_BASE_URL),
      'import.meta.env.VITE_API_PROXY_TARGET': JSON.stringify(env.VITE_API_PROXY_TARGET),
    }
  }
})