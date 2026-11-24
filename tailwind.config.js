/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    "./app/web/templates/**/*.html",
    "./app/api/**/*.py",
  ],
  theme: {
    extend: {
      colors: {
        ink: '#021f27',
        surface: '#062933',
        evergreen: '#013a34',
        deep: '#01161c',
        marine: '#2174c4',
        sage: '#719a72',
        offwhite: '#f0f4f5',
        muted: '#94a8b0',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
    },
  },
  plugins: [],
}
