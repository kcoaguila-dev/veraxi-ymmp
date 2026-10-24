/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: '#0B0F19',
        panel: '#111827',
        layer: '#1F2937',
        hover: '#374151',
        structural: '#1E293B',
        zundamon: '#10B981',
        shikoku: '#F43F5E',
        tsumugi: '#F59E0B'
      },
      fontFamily: {
        sans: ['system-ui', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', '"Hiragino Kaku Gothic ProN"', '"Yu Gothic UI"', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace']
      }
    },
  },
  plugins: [],
}
