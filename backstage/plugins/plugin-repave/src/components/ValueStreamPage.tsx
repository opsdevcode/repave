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

export type ValueStreamHistoryRow = {
  capturedAt: string;
  adoptionRatio: string;
  planApplyRatio: string;
};

export type ValueStreamView = {
  capturedAt: string;
  message: string;
  adoptionRatio: string;
  planApplyRatio: string;
  governedCount: number;
  eligibleCount: number;
  timeToFirstP50: string;
  history: ValueStreamHistoryRow[];
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

export function formatSeconds(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return 'n/a';
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return 'n/a';
  }
  return `${Math.round(numeric)}s`;
}

export function parseValueStreamPayload(body: unknown): ValueStreamView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const history = Array.isArray(record.history)
    ? record.history
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const row = item as Record<string, unknown>;
          return {
            capturedAt: String(row.captured_at ?? ''),
            adoptionRatio: formatRatio(row.adoption_ratio),
            planApplyRatio: formatRatio(row.plan_apply_ratio),
          };
        })
        .filter(row => row.capturedAt)
    : [];
  return {
    capturedAt: String(record.captured_at ?? ''),
    message: String(record.message ?? ''),
    adoptionRatio: formatRatio(record.adoption_ratio),
    planApplyRatio: formatRatio(record.plan_apply_ratio),
    governedCount: Number(record.governed_count ?? 0),
    eligibleCount: Number(record.eligible_count ?? 0),
    timeToFirstP50: formatSeconds(record.time_to_first_artifact_seconds_p50),
    history,
  };
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

const HISTORY_COLUMNS: TableColumn<ValueStreamHistoryRow>[] = [
  { title: 'Captured', field: 'capturedAt' },
  { title: 'Adoption', field: 'adoptionRatio' },
  { title: 'Plan → apply', field: 'planApplyRatio' },
];

export function ValueStreamPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [view, setView] = useState<ValueStreamView | undefined>();
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    const base = await discoveryApi.getBaseUrl('proxy');
    const response = await fetchApi.fetch(`${base}/repave/api/v2/platform/value-stream`);
    const text = await response.text();
    const body = parseJsonBody(text);
    if (!response.ok) {
      throw new Error(
        parseApiDetail(body, `GET /api/v2/platform/value-stream returned ${response.status}`),
      );
    }
    return parseValueStreamPayload(body);
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
        title="Value stream"
        subtitle="DORA-style signals from GET /api/v2/platform/value-stream."
      />
      <Content>
        {error ? <p>{error}</p> : null}
        {view === undefined && !error ? <Progress /> : null}
        {view ? (
          <>
            <InfoCard title="Current">
              <StructuredMetadataTable
                metadata={{
                  Captured: view.capturedAt || 'n/a',
                  Adoption: view.adoptionRatio,
                  Governed: `${view.governedCount} / ${view.eligibleCount}`,
                  'Plan → apply': view.planApplyRatio,
                  'Time to first artifact (p50)': view.timeToFirstP50,
                  ...(view.message ? { Note: view.message } : {}),
                }}
              />
            </InfoCard>
            <Table
              title="History"
              options={{ paging: view.history.length > 12, search: false, padding: 'dense' }}
              columns={HISTORY_COLUMNS}
              data={view.history}
              emptyContent={<p>No snapshots yet.</p>}
            />
          </>
        ) : null}
      </Content>
    </Page>
  );
}
