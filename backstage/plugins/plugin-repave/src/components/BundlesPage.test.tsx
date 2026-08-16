import { parseApiDetail, parseBundleDetail, parseBundlesPayload } from './BundlesPage';

describe('bundles helpers', () => {
  it('maps list rows and a detail with topology', () => {
    const rows = parseBundlesPayload({
      bundles: [
        {
          name: 'service-stack',
          version: '0.2.0',
          description: 'App plus Helm',
          members: [{ id: 'app' }, { id: 'helm' }],
        },
        { version: '1.0.0' },
      ],
    });
    expect(rows).toEqual([
      {
        name: 'service-stack',
        version: '0.2.0',
        description: 'App plus Helm',
        memberCount: 2,
      },
    ]);
    const detail = parseBundleDetail({
      name: 'service-stack',
      version: '0.2.0',
      description: 'App plus Helm',
      members: [{ id: 'app', blueprint: 'app-service-generic' }],
      topology: { edges: [{ source: 'service-stack', target: 'app', label: 'bundle' }] },
    });
    expect(detail?.members[0]?.blueprint).toBe('app-service-generic');
    expect(detail?.edges[0]?.source).toBe('service-stack');
    expect(parseBundleDetail({})).toBeUndefined();
    expect(parseApiDetail({ detail: 'bundle not found: missing' }, 'fallback')).toBe(
      'bundle not found: missing',
    );
  });
});
