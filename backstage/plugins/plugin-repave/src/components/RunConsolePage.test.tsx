import { runConsolePath } from './RunConsolePage';

describe('run console helpers', () => {
  it('builds a query-param console path', () => {
    expect(runConsolePath(' run-3 ')).toBe('/run-console?run=run-3');
    expect(runConsolePath('')).toBe('/run-console');
  });
});
