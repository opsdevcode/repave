import { useCallback, useEffect, useState } from 'react';
import {
  Content,
  Header,
  Page,
  Progress,
  Table,
  type TableColumn,
} from '@backstage/core-components';
import { discoveryApiRef, fetchApiRef, useApi } from '@backstage/core-plugin-api';

export type ActivityRow = {
  timestamp: string;
  event: string;
  blueprint: string;
  moduleName: string;
  mode: string;
  gatesOutcome: string;
  actingUser: string;
  repositoryUrl: string;
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

export function rowsFromEntries(items: unknown[]): ActivityRow[] {
  return items
    .filter(item => item && typeof item === 'object')
    .map(item => {
      const record = item as Record<string, unknown>;
      return {
        timestamp: String(record.timestamp ?? ''),
        event: String(record.event ?? ''),
        blueprint: String(record.blueprint_name ?? ''),
        moduleName: String(record.module_name ?? ''),
        mode: record.dry_run === false ? 'Apply' : 'Plan',
        gatesOutcome: String(record.gates_outcome ?? ''),
        actingUser: String(record.acting_user ?? ''),
        repositoryUrl: String(record.repository_url ?? ''),
      };
    })
    .filter(row => row.timestamp || row.event);
}

export function parseAuditPayload(body: unknown): { total: number; rows: ActivityRow[] } {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const items = Array.isArray(record.entries) ? record.entries : [];
  return { total: Number(record.total ?? 0), rows: rowsFromEntries(items) };
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

const COLUMNS: TableColumn<ActivityRow>[] = [
  { title: 'When', field: 'timestamp' },
  { title: 'Event', field: 'event' },
  { title: 'Blueprint', field: 'blueprint' },
  { title: 'Artifact', field: 'moduleName' },
  { title: 'Mode', field: 'mode' },
  { title: 'Gates', field: 'gatesOutcome' },
  { title: 'User', field: 'actingUser' },
];

export function ActivityPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [rows, setRows] = useState<ActivityRow[] | undefined>();
  const [total, setTotal] = useState(0);
  const [error, setError] = useState('');

  const loadActivity = useCallback(async () => {
    const base = await discoveryApi.getBaseUrl('proxy');
    const response = await fetchApi.fetch(`${base}/repave/api/v2/audit?limit=50`);
    const text = await response.text();
    const body = parseJsonBody(text);
    if (!response.ok) {
      throw new Error(parseApiDetail(body, `GET /api/v2/audit returned ${response.status}`));
    }
    return parseAuditPayload(body);
  }, [discoveryApi, fetchApi]);

  useEffect(() => {
    let cancelled = false;
    loadActivity()
      .then(next => {
        if (!cancelled) {
          setRows(next.rows);
          setTotal(next.total);
          setError('');
        }
      })
      .catch(err => {
        if (!cancelled) {
          setRows(undefined);
          setError(err instanceof Error ? err.message : String(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [loadActivity]);

  return (
    <Page themeId="tool">
      <Header
        title="Activity"
        subtitle="Recent audit events from GET /api/v2/audit. Configure audit.enabled to populate this list."
      />
      <Content>
        {error ? <p>{error}</p> : null}
        {rows === undefined && !error ? <Progress /> : null}
        {rows ? (
          <Table
            title={total ? `${rows.length} of ${total} events` : 'Recent events'}
            options={{ paging: rows.length > 20, search: true, padding: 'dense' }}
            columns={COLUMNS}
            data={rows}
            emptyContent={<p>No audit events yet.</p>}
          />
        ) : null}
      </Content>
    </Page>
  );
}
