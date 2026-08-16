import {
  buildLivePlanBody,
  parseApiDetail,
  parseServiceDetail,
  servicesPath,
} from './ServicesPage';

describe('services helpers', () => {
  it('maps entity detail and builds a live-plan body', () => {
    const view = parseServiceDetail({
      entity_id: 'github.com/acme/tf-app',
      display_name: 'tf-app',
      owner: 'platform',
      blueprint_name: 'terraform-module-generic',
      maturity: { label: 'L2' },
      cost_actuals: { monthly_usd: '12' },
      slo_summary: { status: 'ok' },
      deployment_status: { status: 'healthy' },
      scorecard: [{ key: 'has-slo' }],
    });
    expect(view?.cost).toBe('12');
    expect(view?.lineage).toBe('1 scorecard dimensions');
    expect(buildLivePlanBody(' github.com/acme/tf-app ')).toEqual({
      kind: 'live_plan',
      entity_id: 'github.com/acme/tf-app',
    });
    expect(servicesPath('github.com/acme/tf-app')).toBe(
      '/services?entity=github.com%2Facme%2Ftf-app',
    );
    expect(parseServiceDetail({})).toBeUndefined();
    expect(parseApiDetail({ detail: 'Entity not found' }, 'fallback')).toBe('Entity not found');
  });
});
