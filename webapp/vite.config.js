import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  // Абсолютный base надёжнее в Telegram WebView и при деплое на корень домена (Railway).
  base: '/',
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
})
