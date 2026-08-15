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

export type MetricsFunnelRow = {
  blueprintName: string;
  plans: number;
  applies: number;
  passedApplies: number;
  conversion: string;
};

export type MetricsFrictionRow = {
  blueprintName: string;
  total: number;
  failed: number;
  failRatio: string;
};

export type MetricsView = {
  capturedAt: string;
  message: string;
  auditAvailable: boolean;
  fleetEnabled: boolean;
  eligibleCount: number;
  governedCount: number;
  adoptionRatio: string;
  planCount: number;
  applyCount: number;
  planApplyRatio: string;
  funnels: MetricsFunnelRow[];
  friction: MetricsFrictionRow[];
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

export function formatRatio(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return 'n/a';
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return 'n/a';
  }
  return `${Math.round(numeric * 1000) / 10}%`;
}

export function parseMetricsSnapshot(body: unknown): MetricsView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const funnels = Array.isArray(record.funnels)
    ? record.funnels
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const row = item as Record<string, unknown>;
          return {
            blueprintName: String(row.blueprint_name ?? ''),
            plans: Number(row.plans ?? 0),
            applies: Number(row.applies ?? 0),
            passedApplies: Number(row.passed_applies ?? 0),
            conversion: formatRatio(row.conversion_ratio),
          };
        })
        .filter(row => row.blueprintName)
    : [];
  const friction = Array.isArray(record.friction)
    ? record.friction
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const row = item as Record<string, unknown>;
          return {
            blueprintName: String(row.blueprint_name ?? ''),
            total: Number(row.total ?? 0),
            failed: Number(row.failed ?? 0),
            failRatio: formatRatio(row.fail_ratio),
          };
        })
        .filter(row => row.blueprintName)
    : [];
  return {
    capturedAt: String(record.captured_at ?? ''),
    message: String(record.message ?? ''),
    auditAvailable: Boolean(record.audit_available),
    fleetEnabled: Boolean(record.fleet_enabled),
    eligibleCount: Number(record.eligible_count ?? 0),
    governedCount: Number(record.governed_count ?? 0),
    adoptionRatio: formatRatio(record.adoption_ratio),
    planCount: Number(record.plan_count ?? 0),
    applyCount: Number(record.apply_count ?? 0),
    planApplyRatio: formatRatio(record.plan_apply_ratio),
    funnels,
    friction,
  };
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

const FUNNEL_COLUMNS: TableColumn<MetricsFunnelRow>[] = [
  { title: 'Blueprint', field: 'blueprintName' },
  { title: 'Plans', field: 'plans' },
  { title: 'Applies', field: 'applies' },
  { title: 'Passed', field: 'passedApplies' },
  { title: 'Conversion', field: 'conversion' },
];

const FRICTION_COLUMNS: TableColumn<MetricsFrictionRow>[] = [
  { title: 'Blueprint', field: 'blueprintName' },
  { title: 'Total', field: 'total' },
  { title: 'Failed', field: 'failed' },
  { title: 'Fail rate', field: 'failRatio' },
];

export function MetricsPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [metrics, setMetrics] = useState<MetricsView | undefined>();
  const [error, setError] = useState('');

  const loadMetrics = useCallback(async () => {
    const base = await discoveryApi.getBaseUrl('proxy');
    const response = await fetchApi.fetch(`${base}/repave/api/v2/platform/metrics`);
    const text = await response.text();
    const body = parseJsonBody(text);
    if (!response.ok) {
      throw new Error(
        parseApiDetail(body, `GET /api/v2/platform/metrics returned ${response.status}`),
      );
    }
    return parseMetricsSnapshot(body);
  }, [discoveryApi, fetchApi]);

  useEffect(() => {
    let cancelled = false;
    loadMetrics()
      .then(next => {
        if (!cancelled) {
          setMetrics(next);
          setError('');
        }
      })
      .catch(err => {
        if (!cancelled) {
          setMetrics(undefined);
          setError(err instanceof Error ? err.message : String(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [loadMetrics]);

  return (
    <Page themeId="tool">
      <Header
        title="Adoption"
        subtitle="Golden-path adoption from GET /api/v2/platform/metrics. Admin role when service auth is on."
      />
      <Content>
        {error ? <p>{error}</p> : null}
        {metrics === undefined && !error ? <Progress /> : null}
        {metrics ? (
          <>
            <InfoCard title="Snapshot">
              <StructuredMetadataTable
                metadata={{
                  Captured: metrics.capturedAt || 'n/a',
                  Adoption: metrics.adoptionRatio,
                  Governed: `${metrics.governedCount} / ${metrics.eligibleCount}`,
                  'Plan → apply': metrics.planApplyRatio,
                  Plans: String(metrics.planCount),
                  Applies: String(metrics.applyCount),
                  Fleet: metrics.fleetEnabled ? 'On' : 'Off',
                  Audit: metrics.auditAvailable ? 'On' : 'Off',
                  ...(metrics.message ? { Note: metrics.message } : {}),
                }}
              />
            </InfoCard>
            <Table
              title="Funnels"
              options={{ paging: metrics.funnels.length > 10, search: false, padding: 'dense' }}
              columns={FUNNEL_COLUMNS}
              data={metrics.funnels}
              emptyContent={<p>No blueprint funnels yet.</p>}
            />
            <Table
              title="Friction"
              options={{ paging: metrics.friction.length > 10, search: false, padding: 'dense' }}
              columns={FRICTION_COLUMNS}
              data={metrics.friction}
              emptyContent={<p>No friction rows yet.</p>}
            />
          </>
        ) : null}
      </Content>
    </Page>
  );
}
