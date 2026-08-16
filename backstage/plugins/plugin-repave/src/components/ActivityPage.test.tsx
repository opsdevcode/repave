import { parseApiDetail, parseAuditPayload, rowsFromEntries } from './ActivityPage';

describe('activity helpers', () => {
  it('maps audit entries and labels apply when dry_run is false', () => {
    const rows = rowsFromEntries([
      {
        timestamp: '2026-08-15T12:00:00Z',
        event: 'generate',
        blueprint_name: 'terraform-module-generic',
        module_name: 'tf-vpc',
        dry_run: false,
        gates_outcome: 'passed',
        acting_user: 'builder',
        repository_url: 'https://github.com/acme/tf-vpc',
      },
      {},
    ]);
    expect(rows).toEqual([
      {
        timestamp: '2026-08-15T12:00:00Z',
        event: 'generate',
        blueprint: 'terraform-module-generic',
        moduleName: 'tf-vpc',
        mode: 'Apply',
        gatesOutcome: 'passed',
        actingUser: 'builder',
        repositoryUrl: 'https://github.com/acme/tf-vpc',
      },
    ]);
    const payload = parseAuditPayload({
      total: 1,
      entries: [{ timestamp: '2026-08-15T12:00:00Z', event: 'import', dry_run: true }],
    });
    expect(payload.total).toBe(1);
    expect(payload.rows[0]?.mode).toBe('Plan');
    expect(parseApiDetail({ detail: 'Audit log is not configured' }, 'fallback')).toBe(
      'Audit log is not configured',
    );
  });
});
