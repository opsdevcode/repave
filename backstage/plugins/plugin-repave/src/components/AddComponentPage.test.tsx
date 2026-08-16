import {
  addQueryDefaults,
  buildAddRequest,
  parseAddApply,
  parseAddPlan,
  parseApiDetail,
} from './AddComponentPage';

describe('add-component helpers', () => {
  it('reads checkout, blueprint, and component id from the query string', () => {
    expect(
      addQueryDefaults('?repo=/modules/checkout-api&blueprint=helm-chart-generic&component_id=helm'),
    ).toEqual({
      target: '/modules/checkout-api',
      blueprint: 'helm-chart-generic',
      componentId: 'helm',
    });
    expect(addQueryDefaults('target_repo=/tmp/svc')).toEqual({
      target: '/tmp/svc',
      blueprint: '',
      componentId: '',
    });
  });

  it('requires a checkout and blueprint, then forwards optional id and force', () => {
    expect(buildAddRequest({ target: '', blueprint: 'helm-chart-generic', componentId: '', force: false }).ok).toBe(
      false,
    );
    expect(buildAddRequest({ target: '/modules/svc', blueprint: '', componentId: '', force: false }).ok).toBe(false);
    expect(
      buildAddRequest({
        target: '/modules/checkout-api',
        blueprint: 'helm-chart-generic',
        componentId: 'helm',
        force: true,
      }),
    ).toEqual({
      ok: true,
      body: {
        target_repo: '/modules/checkout-api',
        blueprint: 'helm-chart-generic',
        force: true,
        component_id: 'helm',
      },
    });
  });

  it('parses a plan payload including conflicts', () => {
    const plan = parseAddPlan({
      target: '/modules/checkout-api',
      blueprint_name: 'helm-chart-generic',
      blueprint_version: '1.2.0',
      component_id: 'helm',
      summary: '4 file(s) added, 0 overwritten, 1 conflict(s)',
      ok: false,
      files_added: ['charts/checkout/Chart.yaml'],
      files_overwritten: [],
      conflicts: ['charts/checkout/values.yaml'],
    });
    expect(plan.blueprintName).toBe('helm-chart-generic');
    expect(plan.componentId).toBe('helm');
    expect(plan.ok).toBe(false);
    expect(plan.filesAdded).toEqual(['charts/checkout/Chart.yaml']);
    expect(plan.conflicts).toEqual(['charts/checkout/values.yaml']);
  });

  it('parses apply output and conflict detail objects', () => {
    expect(
      parseAddApply({
        git_branch: 'repave/add/helm-1.2.0',
        commit_sha: 'abc123',
      }),
    ).toEqual({
      gitBranch: 'repave/add/helm-1.2.0',
      commitSha: 'abc123',
    });
    expect(parseApiDetail({ detail: 'target_repo is required' }, 'fallback')).toBe('target_repo is required');
    expect(parseApiDetail({ detail: { conflicts: ['README.md'] } }, 'fallback')).toBe('Conflicts: README.md');
  });
});
