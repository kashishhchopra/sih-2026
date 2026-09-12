/** @type {import('tailwindcss').Config} */
// `slate` (neutral surfaces/text/borders) and `sky` (primary accent) are
// redefined as CSS custom properties rather than fixed hex values, so the
// SAME utility classes already used everywhere (`bg-white dark:bg-slate-800`,
// `bg-sky-600`, `text-slate-500`, ...) can be retinted per dashboard role
// (see src/index.css's `[data-role-theme]` blocks) without touching a single
// component's className. Every other color (red/amber/emerald/etc., used for
// real status meaning -- critical/warning/resolved) is untouched on purpose.
// `:root`'s own values equal Tailwind's real defaults, so any page outside a
// role scope (Login, Register, Landing, ...) renders pixel-identical to before.
function scale(name) {
  const shades = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950]
  return Object.fromEntries(shades.map((s) => [s, `rgb(var(--tw-${name}-${s}) / <alpha-value>)`]))
}

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        slate: scale('slate'),
        sky: scale('sky'),
        brand: {
          DEFAULT: '#0ea5e9',
          dark: '#0369a1',
        },
      },
    },
  },
  plugins: [],
}
