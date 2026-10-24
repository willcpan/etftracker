import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Relative base so the build works at any path (GitHub Pages project site, local preview).
export default defineConfig({
  plugins: [react()],
  base: './',
})
