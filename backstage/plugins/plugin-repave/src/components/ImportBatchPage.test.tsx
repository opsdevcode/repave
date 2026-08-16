import {
  buildBatchRequest,
  buildOrgScanRequest,
  parseBatchApply,
  parseBatchPlan,
  parseOrgScanResult,
  parseTargetLines,
  targetBlueprintsFromScan,
  urlsFromScan,
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

  it('builds an org-scan request and maps classified repos onto the batch', () => {
    expect(
      buildOrgScanRequest({
        org: '',
        topic: '',
        language: '',
        pushedSince: '',
        families: ['terraform'],
        skipGoverned: true,
        excludeArchived: true,
        excludeForks: true,
      }).ok,
    ).toBe(false);
    expect(
      buildOrgScanRequest({
        org: 'acme',
        topic: 'terraform',
        language: 'HCL',
        pushedSince: '2026-01-01',
        families: ['terraform', 'ansible'],
        skipGoverned: true,
        excludeArchived: true,
        excludeForks: true,
      }),
    ).toEqual({
      ok: true,
      body: {
        org: 'acme',
        topic: 'terraform',
        language: 'HCL',
        pushed_since: '2026-01-01',
        families: ['terraform', 'ansible'],
        skip_governed: true,
        exclude_archived: true,
        exclude_forks: true,
      },
    });
    const scan = parseOrgScanResult({
      org: 'acme',
      listed: 2,
      truncated: false,
      discovery_mode: 'search',
      search_query: 'org:acme language:HCL',
      repos: [
        {
          url: 'https://github.com/acme/vpc',
          name: 'vpc',
          governed: false,
          top_candidate: {
            blueprint_name: 'terraform-module-generic',
            family: 'terraform',
            artifact_type: 'terraform-module',
            percent: 92,
          },
        },
        { url: '', name: 'skip' },
      ],
    });
    expect(scan.repos[0]?.percent).toBe('92%');
    expect(urlsFromScan(scan.repos)).toEqual(['https://github.com/acme/vpc']);
    expect(targetBlueprintsFromScan(scan.repos)).toEqual({
      'https://github.com/acme/vpc': 'terraform-module-generic',
    });
    expect(
      buildBatchRequest({
        targets: 'https://github.com/acme/vpc',
        org: 'acme',
        topic: '',
        blueprint: '',
        withGates: true,
        useFamilyBlueprints: true,
        targetBlueprints: targetBlueprintsFromScan(scan.repos),
      }),
    ).toEqual({
      ok: true,
      body: {
        targets: ['https://github.com/acme/vpc'],
        org: 'acme',
        with_gates: true,
        use_family_blueprints: true,
        target_blueprints: { 'https://github.com/acme/vpc': 'terraform-module-generic' },
      },
    });
  });
});
