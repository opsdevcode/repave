import { queryParam } from './queryParam';

describe('queryParam', () => {
  it('reads a trimmed value from a search string', () => {
    expect(queryParam('?family=terraform&owner=platform', 'family')).toBe('terraform');
    expect(queryParam('run=abc', 'run')).toBe('abc');
    expect(queryParam('?slug=%20ops%20', 'slug')).toBe('ops');
    expect(queryParam('', 'run')).toBe('');
  });
});
