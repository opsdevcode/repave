import {
  isActiveRunStatus,
  parseRunDetail,
  parseRunsPayload,
  rowsFromRuns,
} from './RunsPage';

describe('runs helpers', () => {
  it('maps list payloads and drops rows without a run id', () => {
    const rows = rowsFromRuns([
      {
        run_id: 'run-1',
        status: 'succeeded',
        kind: 'environment_vend',
        blueprint: 'terraform-environment-stack',
        dry_run: true,
        acting_user: 'builder',
        updated_at: '2026-08-14T23:00:00Z',
        result: { gates_outcome: 'passed' },
      },
      { status: 'queued' },
    ]);
    expect(rows).toEqual([
      {
        runId: 'run-1',
        status: 'succeeded',
        kind: 'environment_vend',
        blueprint: 'terraform-environment-stack',
        mode: 'Plan',
        actingUser: 'builder',
        updatedAt: '2026-08-14T23:00:00Z',
        error: '',
        gatesOutcome: 'passed',
      },
    ]);
  });

  it('labels apply when dry_run is false', () => {
    const rows = parseRunsPayload({
      runs: [{ run_id: 'run-2', dry_run: false, status: 'running' }],
    });
    expect(rows[0]?.mode).toBe('Apply');
    expect(isActiveRunStatus(rows[0]?.status ?? '')).toBe(true);
  });

  it('parses a single run detail', () => {
    const row = parseRunDetail({
      run_id: 'run-3',
      status: 'failed',
      error: 'gates failed',
      dry_run: true,
    });
    expect(row?.runId).toBe('run-3');
    expect(row?.error).toBe('gates failed');
    expect(isActiveRunStatus('failed')).toBe(false);
  });
});
