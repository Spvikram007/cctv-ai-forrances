/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        surveillance: {
          darkest: '#090d16',
          darker: '#0f172a',
          card: '#1e293b',
          border: '#334155',
          muted: '#64748b',
          accent: '#0284c7',
          online: '#10b981',
          alarm: '#ef4444',
          standby: '#f59e0b',
        }
      }
    },
  },
  plugins: [],
}
