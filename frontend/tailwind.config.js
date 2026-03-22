/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: '#0a0a0f',
          raised: '#12121a',
          overlay: '#1a1a25',
        },
        border: {
          DEFAULT: '#2a2a3a',
          subtle: '#1e1e2e',
        },
        text: {
          primary: '#e8e8f0',
          secondary: '#8888a0',
          muted: '#555570',
        },
        accent: {
          DEFAULT: '#6366f1',
          hover: '#818cf8',
        },
        green: {
          DEFAULT: '#22c55e',
          muted: 'rgba(34, 197, 94, 0.15)',
        },
        red: {
          DEFAULT: '#ef4444',
          muted: 'rgba(239, 68, 68, 0.15)',
        },
        yellow: {
          DEFAULT: '#eab308',
          muted: 'rgba(234, 179, 8, 0.15)',
        },
      },
    },
  },
  plugins: [],
}
