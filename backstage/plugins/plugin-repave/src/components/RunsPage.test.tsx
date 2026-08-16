import {
  canReplayRun,
  isActiveRunStatus,
  parseApiDetail,
  parseRunDetail,
  parseRunsPayload,
  replayPath,
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
        previewFiles: [],
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
      result: { rendered_files: [{ path: 'main.tf', content: 'resource "aws_s3_bucket" "x" {}' }] },
    });
    expect(row?.runId).toBe('run-3');
    expect(row?.error).toBe('gates failed');
    expect(row?.previewFiles[0]?.path).toBe('main.tf');
    expect(isActiveRunStatus('failed')).toBe(false);
  });

  it('allows replay only for failed and dead-letter runs', () => {
    expect(canReplayRun('failed')).toBe(true);
    expect(canReplayRun('dead_letter')).toBe(true);
    expect(canReplayRun('succeeded')).toBe(false);
    expect(canReplayRun('queued')).toBe(false);
    expect(replayPath('run-3')).toBe('/runs/run-3/replay');
    expect(parseApiDetail({ detail: 'only failed or dead_letter runs can be replayed' }, 'fallback')).toBe(
      'only failed or dead_letter runs can be replayed',
    );
  });
});
