import { parseFinOpsExport, rowsFromAnomalies, rowsFromChargeback } from './FinOpsPage';

describe('finops helpers', () => {
  it('maps FOCUS export rows and anomalies', () => {
    const rows = rowsFromChargeback([
      {
        Owner: 'platform',
        ServiceName: 'tf-vpc',
        BillingCurrency: 'USD',
        BilledCost: '12.50',
        MonthlyBudgetUsd: '20.00',
        EntityId: 'tf-vpc',
      },
      {},
    ]);
    expect(rows).toEqual([
      {
        owner: 'platform',
        serviceName: 'tf-vpc',
        billedCost: '12.50',
        currency: 'USD',
        monthlyBudget: '20.00',
        entityId: 'tf-vpc',
      },
    ]);
    expect(
      rowsFromAnomalies([
        {
          entity_id: 'tf-vpc',
          display_name: 'tf-vpc',
          kind: 'spike',
          change_pct: 40.5,
          current_amount: '18.00',
        },
      ])[0]?.kind,
    ).toBe('spike');
    const view = parseFinOpsExport({
      count: 1,
      currency: 'USD',
      rows: [{ ServiceName: 'tf-vpc', EntityId: 'tf-vpc', BilledCost: '1.00' }],
      anomalies: [],
    });
    expect(view.count).toBe(1);
    expect(view.rows[0]?.serviceName).toBe('tf-vpc');
  });
});
