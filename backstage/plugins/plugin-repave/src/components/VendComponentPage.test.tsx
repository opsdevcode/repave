import {
  buildComponentVendRequest,
  isValidComponentName,
  parseComponentKinds,
  rowsFromComponentKinds,
} from './VendComponentPage';

describe('component vend helpers', () => {
  it('maps kinds and drops rows without an id', () => {
    const rows = rowsFromComponentKinds([
      {
        id: 'database',
        label: 'Managed database',
        blueprint: 'terraform-environment-stack',
        description: 'Relational database instance requested through GitOps.',
      },
      { label: 'orphan' },
    ]);
    expect(rows).toEqual([
      {
        id: 'database',
        label: 'Managed database',
        blueprint: 'terraform-environment-stack',
        description: 'Relational database instance requested through GitOps.',
      },
    ]);
  });

  it('parses the /api/v2/component-kinds payload', () => {
    const catalog = parseComponentKinds({
      count: 3,
      vend_available: true,
      kinds: [
        { id: 'queue', label: 'Message queue' },
        { id: 'bucket', label: 'Object bucket' },
      ],
    });
    expect(catalog.vendAvailable).toBe(true);
    expect(catalog.count).toBe(3);
    expect(catalog.rows.map(row => row.id)).toEqual(['queue', 'bucket']);
  });

  it('validates names the same way as the engine', () => {
    expect(isValidComponentName('checkout-db')).toBe(true);
    expect(isValidComponentName('Bad_Name')).toBe(false);
    expect(isValidComponentName('ab')).toBe(false);
  });

  it('builds a vend body or names the field to change', () => {
    expect(
      buildComponentVendRequest({
        kind: 'database',
        name: 'checkout-db',
        owner: 'team-checkout',
        dryRun: true,
      }),
    ).toEqual({
      ok: true,
      body: {
        kind: 'database',
        name: 'checkout-db',
        owner: 'team-checkout',
        dry_run: true,
      },
    });
    expect(
      buildComponentVendRequest({
        kind: 'queue',
        name: 'checkout-jobs',
        owner: '  ',
        dryRun: false,
      }),
    ).toEqual({
      ok: true,
      body: {
        kind: 'queue',
        name: 'checkout-jobs',
        dry_run: false,
      },
    });
    expect(
      buildComponentVendRequest({
        kind: '',
        name: 'checkout-db',
        owner: '',
        dryRun: true,
      }),
    ).toEqual({ ok: false, error: 'Pick a component kind' });
    expect(
      buildComponentVendRequest({
        kind: 'database',
        name: 'Bad_Name',
        owner: '',
        dryRun: true,
      }).ok,
    ).toBe(false);
  });
});
