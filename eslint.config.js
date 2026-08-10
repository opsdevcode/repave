import js from "@eslint/js";
import globals from "globals";

export default [
  {
    ignores: [
      "**/node_modules/**",
      "engine/build/**",
      "engine/.venv/**",
      "**/.venv/**",
    ],
  },
  js.configs.recommended,
  {
    files: ["engine/src/repave_engine/static/**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: {
        ...globals.browser,
        repavePortal: "writable",
        repaveHome: "writable",
      },
    },
    rules: {
      // Legacy portal bundle; migrate incrementally.
      "no-var": "off",
      "no-unused-vars": [
        "error",
        { caughtErrorsIgnorePattern: "^_" },
      ],
      eqeqeq: ["error", "always", { null: "ignore" }],
      "no-eval": "error",
      "no-implied-eval": "error",
      "no-new-func": "error",
      "no-script-url": "error",
    },
  },
  {
    files: ["engine/src/repave_engine/static/**/*.mjs"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        ...globals.browser,
        repavePortal: "readonly",
        repaveHome: "writable",
      },
    },
    rules: {
      "no-unused-vars": [
        "error",
        { caughtErrorsIgnorePattern: "^_" },
      ],
      eqeqeq: ["error", "always", { null: "ignore" }],
      "no-eval": "error",
      "no-implied-eval": "error",
      "no-new-func": "error",
      "no-script-url": "error",
    },
  },
  {
    files: [".github/**/*.mjs"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: globals.node,
    },
  },
];
