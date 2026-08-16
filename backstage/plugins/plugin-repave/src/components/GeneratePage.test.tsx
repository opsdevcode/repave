import { parseApiDetail, parseBlueprintCatalog, scaffolderHref } from './GeneratePage';

describe('generate helpers', () => {
  it('groups catalog blueprints and points create at Scaffolder', () => {
    const catalog = parseBlueprintCatalog({
      count: 2,
      groups: [
        {
          family: 'terraform',
          title: 'Terraform',
          subtitle: 'Modules',
          blueprints: [
            {
              name: 'terraform-module-generic',
              version: '1.0.0',
              artifact_type: 'terraform-module',
              description: 'Generic module',
            },
            { name: '' },
          ],
        },
        { family: '', title: 'skip' },
      ],
    });
    expect(catalog.families).toEqual([
      { family: 'terraform', title: 'Terraform', subtitle: 'Modules', count: 1 },
    ]);
    expect(catalog.rows[0]?.name).toBe('terraform-module-generic');
    expect(scaffolderHref()).toBe('/create');
    expect(parseApiDetail({ detail: 'missing catalog' }, 'fallback')).toBe('missing catalog');
  });
});
