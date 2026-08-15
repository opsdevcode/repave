import {
  parseApiDetail,
  parseEstatePayload,
  rowsFromTiles,
  sparklineLabel,
} from './EstatePage';

describe('estate helpers', () => {
  it('maps tiles and drops rows without a repo URL', () => {
    const rows = rowsFromTiles([
      {
        repo_url: 'https://github.com/acme/tf-vpc',
        title: 'tf-vpc',
        owner: 'platform',
        blueprint_name: 'terraform-module-generic',
        blueprint_label: 'Terraform module',
        operator_phase: 'Ready',
        status_label: 'On golden path',
        freshness: 'fresh',
        freshness_detail: 'On the current golden path',
        sparkline: [1, 1, 0, 2],
      },
      { title: 'orphan' },
    ]);
    expect(rows).toEqual([
      {
        repoUrl: 'https://github.com/acme/tf-vpc',
        title: 'tf-vpc',
        owner: 'platform',
        blueprintName: 'terraform-module-generic',
        blueprintLabel: 'Terraform module',
        operatorPhase: 'Ready',
        statusLabel: 'On golden path',
        freshness: 'fresh',
        freshnessDetail: 'On the current golden path',
        sparkline: '++-.',
      },
    ]);
  });

  it('parses the /api/v2/estate payload and API detail', () => {
    const payload = parseEstatePayload({
      count: 1,
      tiles: [{ repo_url: 'https://github.com/acme/tf-vpc', title: 'tf-vpc', sparkline: [1] }],
    });
    expect(payload.count).toBe(1);
    expect(payload.rows[0]?.title).toBe('tf-vpc');
    expect(sparklineLabel([0, 1, 2])).toBe('-+.');
    expect(
      parseApiDetail(
        { detail: 'Fleet registry is not configured (set fleet.file or REPAVE_FLEET_FILE)' },
        'fallback',
      ),
    ).toBe('Fleet registry is not configured (set fleet.file or REPAVE_FLEET_FILE)');
  });
});
