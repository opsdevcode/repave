import { libraryPath, parseApiDetail, parseLibraryPayload } from './LibraryPage';

describe('library helpers', () => {
  it('maps family tiles and entity rows', () => {
    const view = parseLibraryPayload({
      entity_count: 1,
      owner: 'platform',
      family: 'terraform',
      scorecard: { overall: 'pass' },
      groups: [
        {
          family: 'terraform',
          title: 'Terraform',
          subtitle: 'Modules',
          count: 1,
          entities: [
            {
              entity_id: 'github.com/acme/tf-app',
              display_name: 'tf-app',
              owner: 'platform',
              blueprint_name: 'terraform-module-generic',
              maturity: { label: 'L2', level: 2 },
            },
          ],
        },
      ],
    });
    expect(view.overall).toBe('pass');
    expect(view.families[0]?.count).toBe(1);
    expect(view.entities[0]?.maturity).toBe('L2');
    expect(libraryPath({ family: 'terraform', owner: 'platform' })).toBe(
      '/library?family=terraform&owner=platform',
    );
    expect(libraryPath({})).toBe('/library');
    expect(parseApiDetail({ detail: 'unknown library family' }, 'fallback')).toBe(
      'unknown library family',
    );
  });
});
