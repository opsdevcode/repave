import { buildDriftConfirmRequest, parseStandardsPayload } from './StandardsPage';

describe('standards helpers', () => {
  it('parses drift summaries and builds a confirm request', () => {
    const view = parseStandardsPayload({
      fleet_enabled: true,
      summaries: [
        {
          blueprint_name: 'terraform-module-generic',
          catalog_version: '1.2.0',
          governed_count: 2,
          current_count: 1,
          behind_count: 1,
          behind_repos: [
            {
              repo_url: 'https://github.com/acme/tf-vpc',
              owner: 'platform',
              pin_fields: ['blueprint_version'],
            },
          ],
        },
      ],
    });
    expect(view.fleetEnabled).toBe(true);
    expect(view.rows[0]?.behind).toBe(1);
    expect(view.rows[0]?.repoUrls).toEqual(['https://github.com/acme/tf-vpc']);
    expect(buildDriftConfirmRequest(view.rows[0]?.repoUrls ?? [])).toEqual({
      ok: true,
      body: {
        kind: 'fleet_drift_confirm',
        repo_urls: ['https://github.com/acme/tf-vpc'],
      },
    });
  });
});
