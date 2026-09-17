import path from 'node:path'
import { fileURLToPath } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

import pkg from './package.json' with { type: 'json' }

const root = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: './',
  // **이 빌드가 몇 번인지 굽는다.** 서버가 다른 버전이면 화면이 그것을 말할 수 있어야 한다.
  define: { __APP_VERSION__: JSON.stringify(`v${pkg.version}`) },
  resolve: { alias: { '@': path.resolve(root, 'src') } },
  server: {
    port: 5250,
    strictPort: true,
    // 개발 중에만. 배포에서는 백엔드 한 프로세스가 SPA 까지 서빙한다.
    // **8051 이다. 운영이 8050 을 쓴다.** 둘이 같으면 개발 백엔드를 내린 순간 프록시가
    // 운영 설치본에 붙고, 화면은 그 사실을 말하지 않는다.
    proxy: { '/api': { target: 'http://127.0.0.1:8051', changeOrigin: true } },
  },
  build: {
    outDir: 'dist',
    // three.js 한 덩어리가 크다(`shared/viewer`). 3D 를 보는 화면에서만 받는다.
    chunkSizeWarningLimit: 1200,
  },
})
