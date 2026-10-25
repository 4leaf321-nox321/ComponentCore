import path from 'node:path'
import { fileURLToPath } from 'node:url'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

const root = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(root, 'src') } },
  define: { __APP_VERSION__: JSON.stringify('v0.0.0-test') },
  test: {
    environment: 'happy-dom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // 기계가 바쁘면(다른 빌드 · 시험이 함께 돌면) 화면 시험 몇이 기본 5초를 넘겨 실패했다 — 로직이
    // 아니라 시간 문제다(2026-10-25, 부하 평균 20~27 에서 열 남짓). 넉넉히 둔다.
    testTimeout: 15_000,
  },
})
