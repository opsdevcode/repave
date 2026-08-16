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

export type ComplianceFrictionRow = {
  blueprintName: string;
  total: number;
  failed: number;
  failRatio: string;
  passRatio: string;
};

export type ComplianceView = {
  capturedAt: string;
  message: string;
  gatePassRate: string;
  bypassCount: number;
  bypassRepos: string[];
  friction: ComplianceFrictionRow[];
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

export function parseCompliancePayload(body: unknown): ComplianceView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
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
            passRatio: formatRatio(row.pass_ratio),
          };
        })
        .filter(row => row.blueprintName)
    : [];
  const bypassRepos = Array.isArray(record.bypass_repos)
    ? record.bypass_repos.map(item => String(item)).filter(Boolean)
    : [];
  return {
    capturedAt: String(record.captured_at ?? ''),
    message: String(record.message ?? ''),
    gatePassRate: formatRatio(record.gate_pass_rate),
    bypassCount: Number(record.bypass_count ?? bypassRepos.length),
    bypassRepos,
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

const FRICTION_COLUMNS: TableColumn<ComplianceFrictionRow>[] = [
  { title: 'Blueprint', field: 'blueprintName' },
  { title: 'Total', field: 'total' },
  { title: 'Failed', field: 'failed' },
  { title: 'Fail rate', field: 'failRatio' },
  { title: 'Pass rate', field: 'passRatio' },
];

export function CompliancePage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [view, setView] = useState<ComplianceView | undefined>();
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    const base = await discoveryApi.getBaseUrl('proxy');
    const response = await fetchApi.fetch(`${base}/repave/api/v2/platform/compliance`);
    const text = await response.text();
    const body = parseJsonBody(text);
    if (!response.ok) {
      throw new Error(
        parseApiDetail(body, `GET /api/v2/platform/compliance returned ${response.status}`),
      );
    }
    return parseCompliancePayload(body);
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
        title="Compliance"
        subtitle="Gate pass rate and bypass repos from GET /api/v2/platform/compliance."
      />
      <Content>
        {error ? <p>{error}</p> : null}
        {view === undefined && !error ? <Progress /> : null}
        {view ? (
          <>
            <InfoCard title="Posture">
              <StructuredMetadataTable
                metadata={{
                  Captured: view.capturedAt || 'n/a',
                  'Gate pass rate': view.gatePassRate,
                  Bypasses: String(view.bypassCount),
                  ...(view.message ? { Note: view.message } : {}),
                }}
              />
              {view.bypassRepos.length ? (
                <ul>
                  {view.bypassRepos.map(repo => (
                    <li key={repo}>
                      <code>{repo}</code>
                    </li>
                  ))}
                </ul>
              ) : null}
            </InfoCard>
            <Table
              title="Friction"
              options={{ paging: view.friction.length > 10, search: false, padding: 'dense' }}
              columns={FRICTION_COLUMNS}
              data={view.friction}
              emptyContent={<p>No friction rows yet.</p>}
            />
          </>
        ) : null}
      </Content>
    </Page>
  );
}
