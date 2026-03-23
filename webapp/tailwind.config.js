/** @type {import('tailwindcss').Config} */
/** Палитра под аватар AntiSpam Guardian: лайм маскота, тёмный «серверный» фон, неон красный и циан. */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        primary: {
          50: '#f4fce9',
          100: '#e8f9d4',
          200: '#d2f2a8',
          300: '#b4e86d',
          400: '#9fdd3d',
          500: '#8fd41a',
          600: '#6fa814',
          700: '#567f12',
          800: '#466412',
          900: '#3c5514',
        },
        guardian: {
          ink: '#0a0a0c',
          surface: '#0b0b10',
          elevated: '#12121c',
          'elevated-hi': '#1c1c2a',
          red: '#ff3355',
          cyan: '#22ddee',
        },
      },
      boxShadow: {
        'glow-lime': '0 0 24px -4px rgba(143, 212, 26, 0.35)',
        'glow-cyan': '0 0 20px -6px rgba(34, 221, 238, 0.25)',
      },
    },
  },
  plugins: [],
}
