import { formatRatio, parseApiDetail, parseMetricsSnapshot } from './MetricsPage';

describe('metrics helpers', () => {
  it('formats ratios and parses a snapshot', () => {
    expect(formatRatio(0.7532)).toBe('75.3%');
    expect(formatRatio(null)).toBe('n/a');
    const metrics = parseMetricsSnapshot({
      captured_at: '2026-08-15T12:00:00Z',
      audit_available: true,
      fleet_enabled: true,
      eligible_count: 10,
      governed_count: 4,
      adoption_ratio: 0.4,
      plan_count: 8,
      apply_count: 3,
      plan_apply_ratio: 0.375,
      message: '',
      funnels: [
        {
          blueprint_name: 'terraform-module-generic',
          plans: 5,
          applies: 2,
          passed_applies: 2,
          conversion_ratio: 0.4,
        },
      ],
      friction: [{ blueprint_name: 'terraform-module-generic', total: 5, failed: 1, fail_ratio: 0.2 }],
    });
    expect(metrics.adoptionRatio).toBe('40%');
    expect(metrics.funnels[0]?.conversion).toBe('40%');
    expect(metrics.friction[0]?.failed).toBe(1);
    expect(parseApiDetail({ detail: 'platform_metrics is not configured' }, 'fallback')).toBe(
      'platform_metrics is not configured',
    );
  });
});
