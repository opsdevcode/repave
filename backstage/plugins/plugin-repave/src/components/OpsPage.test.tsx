import { buildEnvReclaimRunBody, parseApiDetail, parseOpsPayload } from './OpsPage';

describe('ops helpers', () => {
  it('parses readiness, doctor rows, and dead letters', () => {
    const view = parseOpsPayload({
      queued_runs: 2,
      running_runs: 1,
      queue_depth: 3,
      async_generation_enabled: true,
      environment_vending_enabled: true,
      environment_count: 4,
      readiness: { status: 'ready' },
      reclaim_preview: { count: 1 },
      doctor_results: [{ tool: 'terraform', present: true, detected_version: '1.9.0' }],
      dead_letter_runs: [{ run_id: 'run-1', status: 'dead_letter', kind: 'generate' }],
    });
    expect(view.ready).toBe('ready');
    expect(view.queuedRuns).toBe(2);
    expect(view.reclaimCount).toBe('1');
    expect(view.doctor[0]?.tool).toBe('terraform');
    expect(view.deadLetters[0]?.runId).toBe('run-1');
    expect(buildEnvReclaimRunBody()).toEqual({ kind: 'environment_reclaim', dry_run: false });
    expect(parseApiDetail({ detail: 'environment_vending is not enabled' }, 'fallback')).toBe(
      'environment_vending is not enabled',
    );
  });
});
