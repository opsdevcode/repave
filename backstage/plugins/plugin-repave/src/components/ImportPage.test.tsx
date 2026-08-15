import {
  buildImportRequest,
  importQueryDefaults,
  parseApiDetail,
  parseImportApply,
  parseImportPlan,
} from './ImportPage';

describe('import helpers', () => {
  it('reads repo and blueprint from the query string', () => {
    expect(importQueryDefaults('?repo=https://github.com/acme/legacy-vpc&blueprint=terraform-module-generic')).toEqual({
      target: 'https://github.com/acme/legacy-vpc',
      blueprint: 'terraform-module-generic',
    });
    expect(importQueryDefaults('target_repo=https://github.com/acme/x')).toEqual({
      target: 'https://github.com/acme/x',
      blueprint: '',
    });
  });

  it('requires a target and forwards optional blueprint and gates', () => {
    expect(buildImportRequest({ target: '', blueprint: '', withGates: true }).ok).toBe(false);
    expect(
      buildImportRequest({
        target: 'https://github.com/acme/legacy-vpc',
        blueprint: 'terraform-module-generic',
        withGates: false,
      }),
    ).toEqual({
      ok: true,
      body: {
        target_repo: 'https://github.com/acme/legacy-vpc',
        blueprint: 'terraform-module-generic',
        with_gates: false,
      },
    });
  });

  it('parses a plan payload including scorecard and moves', () => {
    const plan = parseImportPlan({
      target: '/tmp/legacy-vpc',
      blueprint_name: 'terraform-module-generic',
      blueprint_version: '0.9.0',
      summary: '1 file(s) moved, 2 scaffold file(s) added, 0 unmapped',
      ok: true,
      detected: true,
      preview_limited: false,
      scorecard: { passing_before: 1, passing_after: 4 },
      moves: [{ source: 'terraform/main.tf', destination: 'main.tf', reason: 'layout' }],
      scaffold_added: ['repave.yaml'],
      unmapped: [],
      conflicts: [],
      gates: [{ name: 'ruff', passed: true, skipped: false, message: '' }],
    });
    expect(plan.blueprintName).toBe('terraform-module-generic');
    expect(plan.passingAfter).toBe(4);
    expect(plan.moves[0]?.destination).toBe('main.tf');
    expect(plan.scaffoldAdded).toEqual(['repave.yaml']);
    expect(plan.gates[0]?.passed).toBe(true);
  });

  it('parses apply output and API detail', () => {
    expect(
      parseImportApply({
        pull_request_url: 'https://github.com/acme/legacy-vpc/pull/3',
        git_branch: 'repave/import-legacy-vpc',
        fleet_registered: true,
      }),
    ).toEqual({
      pullRequestUrl: 'https://github.com/acme/legacy-vpc/pull/3',
      gitBranch: 'repave/import-legacy-vpc',
      fleetRegistered: true,
    });
    expect(parseApiDetail({ detail: 'target_repo is required' }, 'fallback')).toBe(
      'target_repo is required',
    );
  });
});
