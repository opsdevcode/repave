import { portalHomeHref, portalMarkHref, portalNavHref } from './portalNav';

describe('portal nav hrefs', () => {
  it('builds workbench links against a local portal base', () => {
    expect(portalHomeHref('http://127.0.0.1:8089/')).toBe('http://127.0.0.1:8089');
    expect(portalNavHref('http://127.0.0.1:8089', '/library')).toBe(
      'http://127.0.0.1:8089/library',
    );
    expect(portalNavHref('http://127.0.0.1:8089', '/update')).toBe(
      'http://127.0.0.1:8089/update',
    );
  });

  it('uses root-relative hrefs when the portal is same-host', () => {
    expect(portalHomeHref('/')).toBe('/');
    expect(portalNavHref('/', '/library')).toBe('/library');
    expect(portalMarkHref('/')).toBe('/static/brand/svg/repave-mark-dark.svg');
  });

  it('prefers a configured logo URL', () => {
    expect(portalMarkHref('/', 'https://cdn.example.com/mark.svg')).toBe(
      'https://cdn.example.com/mark.svg',
    );
  });
});
