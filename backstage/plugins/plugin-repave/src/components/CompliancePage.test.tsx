import { formatRatio, parseApiDetail, parseCompliancePayload } from './CompliancePage';

describe('compliance helpers', () => {
  it('parses gate pass rate, bypasses, and friction', () => {
    const view = parseCompliancePayload({
      captured_at: '2026-08-15T12:00:00Z',
      gate_pass_rate: 0.8,
      bypass_count: 1,
      bypass_repos: ['https://github.com/acme/shadow'],
      friction: [
        {
          blueprint_name: 'terraform-module-generic',
          total: 5,
          failed: 1,
          fail_ratio: 0.2,
          pass_ratio: 0.8,
        },
      ],
      message: '',
    });
    expect(view.gatePassRate).toBe('80%');
    expect(view.bypassRepos).toEqual(['https://github.com/acme/shadow']);
    expect(view.friction[0]?.passRatio).toBe('80%');
    expect(formatRatio(null)).toBe('n/a');
    expect(parseApiDetail({ detail: 'platform_metrics is not configured' }, 'fallback')).toBe(
      'platform_metrics is not configured',
    );
  });
});
