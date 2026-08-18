import {
  githubSourceUrl,
  hasRepaveLineage,
  portalGenerateHref,
  portalHomeHref,
  portalUpgradeHref,
} from './RepaveLineageCard';

describe('hasRepaveLineage', () => {
  it('is true when the blueprint annotation is present', () => {
    expect(hasRepaveLineage({ 'repave.dev/blueprint': 'terraform-module-generic' })).toBe(
      true,
    );
  });

  it('is false without lineage annotations', () => {
    expect(hasRepaveLineage({})).toBe(false);
    expect(hasRepaveLineage(undefined)).toBe(false);
  });
});

describe('portal handoff hrefs', () => {
  it('builds generate and upgrade links against the portal base', () => {
    expect(portalGenerateHref('http://127.0.0.1:8089', 'terraform-module-generic')).toBe(
      'http://127.0.0.1:8089/blueprints/terraform-module-generic',
    );
    expect(portalUpgradeHref('http://127.0.0.1:8089/')).toBe(
      'http://127.0.0.1:8089/update',
    );
  });

  it('uses a root-relative portal when the base is /', () => {
    expect(portalHomeHref('/')).toBe('/');
    expect(portalGenerateHref('/', 'helm-chart-generic')).toBe(
      '/blueprints/helm-chart-generic',
    );
    expect(portalGenerateHref('/', '')).toBe('/');
    expect(portalUpgradeHref('/')).toBe('/update');
  });
});

describe('githubSourceUrl', () => {
  it('builds a repo URL from project-slug or source-location', () => {
    expect(
      githubSourceUrl({ 'github.com/project-slug': 'acme/checkout' }),
    ).toBe('https://github.com/acme/checkout');
    expect(
      githubSourceUrl({
        'backstage.io/source-location': 'url:https://github.com/acme/other',
      }),
    ).toBe('https://github.com/acme/other');
    expect(githubSourceUrl({})).toBeUndefined();
  });
});
