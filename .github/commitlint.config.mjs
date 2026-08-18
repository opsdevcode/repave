export default {
  extends: ['@commitlint/config-conventional'],
  // Dependabot commit bodies include unwrapped compare URLs.
  ignores: [(message) => message.includes('Signed-off-by: dependabot[bot]')],
  rules: {
    'subject-case': [2, 'never', ['start-case', 'pascal-case', 'upper-case']],
    'header-max-length': [2, 'always', 100],
    // Allow `merge:` on leftover merge commits.
    'type-enum': [
      2,
      'always',
      [
        'build',
        'chore',
        'ci',
        'docs',
        'feat',
        'fix',
        'merge',
        'perf',
        'refactor',
        'revert',
        'style',
        'test',
      ],
    ],
  },
};
