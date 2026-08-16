import {
  buildBatchRequest,
  parseBatchApply,
  parseBatchPlan,
  parseTargetLines,
} from './ImportBatchPage';

describe('batch import helpers', () => {
  it('splits target lines and requires URLs or an org', () => {
    expect(parseTargetLines('https://github.com/acme/a\n\nhttps://github.com/acme/b')).toEqual([
      'https://github.com/acme/a',
      'https://github.com/acme/b',
    ]);
    expect(
      buildBatchRequest({
        targets: '',
        org: '',
        topic: '',
        blueprint: '',
        withGates: true,
        useFamilyBlueprints: false,
      }).ok,
    ).toBe(false);
    expect(
      buildBatchRequest({
        targets: 'https://github.com/acme/legacy-vpc',
        org: 'acme',
        topic: 'terraform',
        blueprint: 'terraform-module-generic',
        withGates: false,
        useFamilyBlueprints: true,
      }),
    ).toEqual({
      ok: true,
      body: {
        targets: ['https://github.com/acme/legacy-vpc'],
        org: 'acme',
        topic: 'terraform',
        blueprint: 'terraform-module-generic',
        with_gates: false,
        use_family_blueprints: true,
      },
    });
  });

  it('parses batch plan and apply payloads', () => {
    const plan = parseBatchPlan({
      count: 1,
      ok: false,
      items: [
        {
          target: 'https://github.com/acme/legacy-vpc',
          blueprint_name: 'terraform-module-generic',
          summary: '1 file(s) moved',
          ok: true,
        },
      ],
      failures: [{ target: 'https://github.com/acme/broken', error: 'already governed' }],
    });
    expect(plan.items[0]?.blueprintName).toBe('terraform-module-generic');
    expect(plan.failures[0]?.error).toBe('already governed');
    const apply = parseBatchApply({
      count: 1,
      ok: true,
      items: [
        {
          plan: { target: 'https://github.com/acme/legacy-vpc' },
          pull_request_url: 'https://github.com/acme/legacy-vpc/pull/3',
          git_branch: 'repave/import-legacy-vpc',
        },
      ],
      failures: [],
      fleet_registered: [true],
    });
    expect(apply.items[0]?.pullRequestUrl).toContain('/pull/3');
    expect(apply.fleetRegistered).toBe(1);
  });
});
