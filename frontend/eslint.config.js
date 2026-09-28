import js from '@eslint/js'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import globals from 'globals'

export default [
  { ignores: ['dist/**', 'coverage/**', 'dev-dist/**'] },
  js.configs.recommended,
  {
    files: ['src/**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: { ...globals.browser, ...globals.es2021 },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: { react, 'react-hooks': reactHooks },
    settings: { react: { version: 'detect' } },
    rules: {
      ...react.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      'react/react-in-jsx-scope': 'off',
      'react/prop-types': 'off',
      // Copy throughout this app is full of contractions/quotes in JSX text
      // nodes; HTML-entity-escaping every apostrophe is not worth the churn.
      'react/no-unescaped-entities': 'off',
      // TouristApp.jsx and a few others have deliberate partial dependency
      // arrays (e.g. tracking effects that shouldn't re-run on every score
      // update) -- warn rather than block the build on those.
      'react-hooks/exhaustive-deps': 'warn',
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    },
  },
  {
    files: ['src/**/*.test.{js,jsx}', 'src/test/**/*.js'],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node, ...globals.es2021, vi: 'readonly' },
    },
  },
]
