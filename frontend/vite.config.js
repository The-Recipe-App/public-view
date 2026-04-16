import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  const serverUrl = env.VITE_SERVER_URL || "http://127.0.0.1:8000";

  return {
    plugins: [
      react(),
      VitePWA({
        registerType: 'autoUpdate',
        includeAssets: ['favicon.ico', 'site_logo_text.svg'],
        manifest: {
          name: 'Forkit',
          short_name: 'Forkit',
          description: 'Discover, fork, and share recipes',
          theme_color: '#f97316',
          background_color: '#0a0a0a',
          display: 'standalone',
          orientation: 'portrait',
          scope: '/',
          start_url: '/',
          icons: [
            {
              src: 'web-logo-transp.svg',
              sizes: 'any',
              type: 'image/svg+xml',
              purpose: 'any maskable',
            },
          ],
        },
        workbox: {
          globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
          runtimeCaching: [
            {
              urlPattern: /^https:\/\/forkit\.up\.railway\.app\/api\/v1\/recipes\/feed/,
              handler: 'NetworkFirst',
              options: {
                cacheName: 'recipe-feed',
                expiration: { maxEntries: 50, maxAgeSeconds: 60 * 60 },
              },
            },
            {
              urlPattern: /^https:\/\/forkit\.up\.railway\.app\/api\/v1\/recipes\/\d+/,
              handler: 'StaleWhileRevalidate',
              options: {
                cacheName: 'recipe-detail',
                expiration: { maxEntries: 100, maxAgeSeconds: 60 * 60 * 24 },
              },
            },
          ],
        },
      }),
    ],
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            "vendor-react": ["react", "react-dom", "react-router-dom"],
            "vendor-query": ["@tanstack/react-query"],
            "vendor-motion": ["framer-motion"],
            "vendor-ui": ["lucide-react", "@headlessui/react"],
            "vendor-auth": ["@simplewebauthn/browser", "jwt-decode"],
            "vendor-markdown": ["react-markdown", "remark-gfm"],
          },
        },
      },
    },

    optimizeDeps: {
      include: ["swiper"],
    },

    server: {
      host: "0.0.0.0",
      port: 5173,
      allowedHosts: ["forkit-frontend.onrender.com", "habitual-uncircular-dia.ngrok-free.dev"],

      proxy: {
        "/api": {
          target: serverUrl,
          changeOrigin: true,
          secure: false,
        },

        "/static": {
          target: serverUrl,
          changeOrigin: true,
          secure: false,
        },
        "/admin": {
          target: serverUrl, // or http://127.0.0.1:8000
          changeOrigin: false,
          secure: false,
          ws: true,
        },
      },
    },

    preview: {
      allowedHosts: ["forkit-frontend.onrender.com", "habitual-uncircular-dia.ngrok-free.dev"],
      host: "0.0.0.0",
    },

    define: {
      global: {},
    },

    resolve: {
      alias: {
        crypto: "crypto-browserify",
        buffer: "buffer",
      },
    },
  };
});
