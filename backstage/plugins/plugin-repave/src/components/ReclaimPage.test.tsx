import { buildReclaimRequest, parseReclaimSummary } from './ReclaimPage';

describe('reclaim helpers', () => {
  it('builds a dry-run or apply body and maps the summary', () => {
    expect(buildReclaimRequest({ dryRun: true, stackName: '' })).toEqual({
      ok: true,
      body: { dry_run: true },
    });
    expect(buildReclaimRequest({ dryRun: false, stackName: 'sandbox-alice' })).toEqual({
      ok: true,
      body: { dry_run: false, stack_name: 'sandbox-alice' },
    });
    const view = parseReclaimSummary({
      count: 2,
      reclaimed: 1,
      decommission_review: 0,
      finalized: 0,
      skipped: 1,
      results: [
        {
          stack_name: 'sandbox-alice',
          entity_id: 'env-alice',
          mode: 'auto_reclaim',
          reclaimed: true,
          skipped: false,
          detail: 'opened decommission PR',
          pull_request_url: 'https://github.com/acme/gitops/pull/9',
        },
        {
          stack_name: 'sandbox-bob',
          entity_id: 'env-bob',
          mode: 'auto_reclaim',
          reclaimed: false,
          skipped: true,
          skip_reason: 'not expired',
        },
      ],
    });
    expect(view.reclaimed).toBe(1);
    expect(view.results[0]?.status).toBe('reclaimed');
    expect(view.results[1]?.status).toBe('skipped');
    expect(view.results[1]?.detail).toBe('not expired');
  });
});
