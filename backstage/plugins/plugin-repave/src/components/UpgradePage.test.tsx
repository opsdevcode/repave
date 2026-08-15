import {
  buildPlanRequest,
  looksLikeRepoUrl,
  parseUpgradePlan,
} from './UpgradePage';

describe('upgrade helpers', () => {
  it('sends local paths as target_repo and URLs as repo_url', () => {
    expect(looksLikeRepoUrl('/path/to/tf-aws-demo')).toBe(false);
    expect(looksLikeRepoUrl('https://github.com/acme/tf-aws-demo')).toBe(true);
    expect(
      buildPlanRequest({
        target: '/path/to/tf-aws-demo',
        blueprint: 'terraform-module-generic',
      }),
    ).toEqual({
      ok: true,
      body: {
        target_repo: '/path/to/tf-aws-demo',
        blueprint: 'terraform-module-generic',
      },
    });
    expect(
      buildPlanRequest({
        target: 'https://github.com/acme/tf-aws-demo',
        blueprint: '',
      }),
    ).toEqual({
      ok: true,
      body: { repo_url: 'https://github.com/acme/tf-aws-demo' },
    });
    expect(buildPlanRequest({ target: '  ', blueprint: '' }).ok).toBe(false);
  });

  it('maps the /api/v2/upgrades/plan payload including auto-merge', () => {
    const plan = parseUpgradePlan({
      blueprint_name: 'terraform-module-generic',
      blueprint_version: '1.2.3',
      changed_file_count: 2,
      summary: '2 file(s) differ',
      added: ['README.md'],
      modified: ['repave.yaml'],
      removed: [],
      auto_merge: { allowed: true, reason: 'mechanical pin bump' },
    });
    expect(plan.blueprintName).toBe('terraform-module-generic');
    expect(plan.changedFileCount).toBe(2);
    expect(plan.added).toEqual(['README.md']);
    expect(plan.autoMergeAllowed).toBe(true);
    expect(plan.autoMergeReason).toBe('mechanical pin bump');
  });
});
