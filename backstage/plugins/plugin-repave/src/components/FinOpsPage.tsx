import { useCallback, useEffect, useState } from 'react';
import {
  Content,
  Header,
  InfoCard,
  Page,
  Progress,
  StructuredMetadataTable,
  Table,
  type TableColumn,
} from '@backstage/core-components';
import { discoveryApiRef, fetchApiRef, useApi } from '@backstage/core-plugin-api';

export type FinOpsChargebackRow = {
  owner: string;
  serviceName: string;
  billedCost: string;
  currency: string;
  monthlyBudget: string;
  entityId: string;
};

export type FinOpsAnomalyRow = {
  entityId: string;
  displayName: string;
  kind: string;
  changePct: string;
  currentAmount: string;
};

export type FinOpsView = {
  count: number;
  currency: string;
  rows: FinOpsChargebackRow[];
  anomalies: FinOpsAnomalyRow[];
};

export function parseApiDetail(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = String((body as { detail: unknown }).detail).trim();
    if (detail) {
      return detail;
    }
  }
  return fallback;
}

export function rowsFromChargeback(items: unknown[]): FinOpsChargebackRow[] {
  return items
    .filter(item => item && typeof item === 'object')
    .map(item => {
      const record = item as Record<string, unknown>;
      return {
        owner: String(record.Owner ?? ''),
        serviceName: String(record.ServiceName ?? ''),
        billedCost: String(record.BilledCost ?? ''),
        currency: String(record.BillingCurrency ?? ''),
        monthlyBudget: String(record.MonthlyBudgetUsd ?? ''),
        entityId: String(record.EntityId ?? ''),
      };
    })
    .filter(row => row.entityId || row.serviceName);
}

export function rowsFromAnomalies(items: unknown[]): FinOpsAnomalyRow[] {
  return items
    .filter(item => item && typeof item === 'object')
    .map(item => {
      const record = item as Record<string, unknown>;
      return {
        entityId: String(record.entity_id ?? ''),
        displayName: String(record.display_name ?? record.entity_id ?? ''),
        kind: String(record.kind ?? ''),
        changePct: `${record.change_pct ?? ''}`,
        currentAmount: String(record.current_amount ?? ''),
      };
    })
    .filter(row => row.entityId);
}

export function parseFinOpsExport(body: unknown): FinOpsView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const rows = Array.isArray(record.rows) ? rowsFromChargeback(record.rows) : [];
  const anomalies = Array.isArray(record.anomalies) ? rowsFromAnomalies(record.anomalies) : [];
  return {
    count: Number(record.count ?? rows.length),
    currency: String(record.currency ?? ''),
    rows,
    anomalies,
  };
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

const CHARGEBACK_COLUMNS: TableColumn<FinOpsChargebackRow>[] = [
  { title: 'Owner', field: 'owner' },
  { title: 'Service', field: 'serviceName' },
  { title: 'Cost (30d)', field: 'billedCost' },
  { title: 'Currency', field: 'currency' },
  { title: 'Budget', field: 'monthlyBudget' },
];

const ANOMALY_COLUMNS: TableColumn<FinOpsAnomalyRow>[] = [
  { title: 'Service', field: 'displayName' },
  { title: 'Kind', field: 'kind' },
  { title: 'Change %', field: 'changePct' },
  { title: 'Current', field: 'currentAmount' },
];

export function FinOpsPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [view, setView] = useState<FinOpsView | undefined>();
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    const base = await discoveryApi.getBaseUrl('proxy');
    const response = await fetchApi.fetch(
      `${base}/repave/api/v2/platform/finops/export?format=json&detect_anomalies=1`,
    );
    const text = await response.text();
    const body = parseJsonBody(text);
    if (!response.ok) {
      throw new Error(
        parseApiDetail(body, `GET /api/v2/platform/finops/export returned ${response.status}`),
      );
    }
    return parseFinOpsExport(body);
  }, [discoveryApi, fetchApi]);

  useEffect(() => {
    let cancelled = false;
    load()
      .then(next => {
        if (!cancelled) {
          setView(next);
          setError('');
        }
      })
      .catch(err => {
        if (!cancelled) {
          setView(undefined);
          setError(err instanceof Error ? err.message : String(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [load]);

  return (
    <Page themeId="tool">
      <Header
        title="FinOps"
        subtitle="Chargeback rows from GET /api/v2/platform/finops/export. CSV download stays on the API."
      />
      <Content>
        {error ? <p>{error}</p> : null}
        {view === undefined && !error ? <Progress /> : null}
        {view ? (
          <>
            <InfoCard title="Export">
              <StructuredMetadataTable
                metadata={{
                  Rows: String(view.count),
                  Currency: view.currency || 'n/a',
                  Anomalies: String(view.anomalies.length),
                }}
              />
            </InfoCard>
            <Table
              title="Chargeback"
              options={{ paging: view.rows.length > 20, search: true, padding: 'dense' }}
              columns={CHARGEBACK_COLUMNS}
              data={view.rows}
              emptyContent={<p>No chargeback rows yet.</p>}
            />
            <Table
              title="Anomalies"
              options={{ paging: view.anomalies.length > 10, search: true, padding: 'dense' }}
              columns={ANOMALY_COLUMNS}
              data={view.anomalies}
              emptyContent={<p>No cost anomalies detected.</p>}
            />
          </>
        ) : null}
      </Content>
    </Page>
  );
}
