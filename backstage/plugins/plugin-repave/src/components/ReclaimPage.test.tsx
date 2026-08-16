import {
  buildComponentReclaimRequest,
  buildReclaimRequest,
  parseComponentReclaimSummary,
  parseReclaimSummary,
} from './ReclaimPage';

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

  it('builds a component reclaim body and maps the summary', () => {
    expect(buildComponentReclaimRequest({ dryRun: true, name: '', kind: '' })).toEqual({
      ok: true,
      body: { dry_run: true },
    });
    expect(
      buildComponentReclaimRequest({
        dryRun: false,
        name: 'checkout-db',
        kind: 'database',
      }),
    ).toEqual({
      ok: true,
      body: { dry_run: false, name: 'checkout-db', kind: 'database' },
    });
    const view = parseComponentReclaimSummary({
      count: 2,
      reclaimed: 1,
      decommission_review: 0,
      finalized: 0,
      skipped: 1,
      results: [
        {
          name: 'checkout-db',
          kind: 'database',
          entity_id: 'cmp-database-checkout-db',
          mode: 'auto_reclaim',
          reclaimed: true,
          skipped: false,
          detail: 'opened decommission PR',
          pull_request_url: 'https://github.com/acme/gitops/pull/11',
        },
        {
          name: 'checkout-jobs',
          kind: 'queue',
          entity_id: 'cmp-queue-checkout-jobs',
          mode: 'auto_reclaim',
          reclaimed: false,
          skipped: true,
          skip_reason: 'not expired',
        },
      ],
    });
    expect(view.reclaimed).toBe(1);
    expect(view.results[0]?.status).toBe('reclaimed');
    expect(view.results[0]?.kind).toBe('database');
    expect(view.results[1]?.status).toBe('skipped');
    expect(view.results[1]?.detail).toBe('not expired');
  });
});
