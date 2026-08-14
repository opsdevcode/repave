import { useCallback, useEffect, useState } from 'react';
import {
  Content,
  Header,
  InfoCard,
  Page,
  Progress,
  StatusError,
  StatusOK,
  StatusPending,
  StatusRunning,
  Table,
  type TableColumn,
} from '@backstage/core-components';
import { discoveryApiRef, fetchApiRef, useApi } from '@backstage/core-plugin-api';

const ACTIVE_STATUSES = new Set(['queued', 'running']);
const POLL_MS = 5_000;

export type RunRow = {
  runId: string;
  status: string;
  kind: string;
  blueprint: string;
  mode: string;
  actingUser: string;
  updatedAt: string;
  error: string;
  gatesOutcome: string;
};

export function isActiveRunStatus(status: string): boolean {
  return ACTIVE_STATUSES.has(status);
}

export function rowsFromRuns(items: unknown[]): RunRow[] {
  return items
    .filter(item => item && typeof item === 'object')
    .map(item => {
      const record = item as Record<string, unknown>;
      const result =
        record.result && typeof record.result === 'object'
          ? (record.result as Record<string, unknown>)
          : {};
      return {
        runId: String(record.run_id ?? ''),
        status: String(record.status ?? ''),
        kind: String(record.kind ?? ''),
        blueprint: String(record.blueprint ?? ''),
        mode: record.dry_run === false ? 'Apply' : 'Plan',
        actingUser: String(record.acting_user ?? ''),
        updatedAt: String(record.updated_at ?? record.created_at ?? ''),
        error: String(record.error ?? ''),
        gatesOutcome: String(result.gates_outcome ?? ''),
      };
    })
    .filter(row => row.runId);
}

export function parseRunsPayload(body: unknown): RunRow[] {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const items = Array.isArray(record.runs) ? record.runs : [];
  return rowsFromRuns(items);
}

export function parseRunDetail(body: unknown): RunRow | undefined {
  const rows = rowsFromRuns([body]);
  return rows[0];
}

function statusChip(status: string) {
  switch (status) {
    case 'succeeded':
      return <StatusOK>Succeeded</StatusOK>;
    case 'running':
      return <StatusRunning>Running</StatusRunning>;
    case 'queued':
      return <StatusPending>Queued</StatusPending>;
    case 'failed':
    case 'dead_letter':
      return <StatusError>{status === 'dead_letter' ? 'Dead letter' : 'Failed'}</StatusError>;
    default:
      return status;
  }
}

const COLUMNS: TableColumn<RunRow>[] = [
  { title: 'Run', field: 'runId' },
  { title: 'Status', field: 'status', render: row => statusChip(row.status) },
  { title: 'Kind', field: 'kind' },
  { title: 'Blueprint', field: 'blueprint' },
  { title: 'Mode', field: 'mode' },
  { title: 'User', field: 'actingUser' },
  { title: 'Updated', field: 'updatedAt' },
];

export function RunsPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [rows, setRows] = useState<RunRow[] | undefined>();
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<RunRow | undefined>();
  const [detailError, setDetailError] = useState('');

  const loadRuns = useCallback(async () => {
    const base = await discoveryApi.getBaseUrl('proxy');
    const response = await fetchApi.fetch(`${base}/repave/api/v2/runs?limit=50`);
    const text = await response.text();
    let body: unknown = {};
    try {
      body = text ? JSON.parse(text) : {};
    } catch {
      body = { detail: text };
    }
    if (!response.ok) {
      const detail =
        body && typeof body === 'object' && 'detail' in body
          ? String((body as { detail: unknown }).detail)
          : text;
      throw new Error(`GET /api/v2/runs returned ${response.status}: ${detail}`);
    }
    return parseRunsPayload(body);
  }, [discoveryApi, fetchApi]);

  useEffect(() => {
    let cancelled = false;
    const refresh = () => {
      loadRuns()
        .then(next => {
          if (!cancelled) {
            setRows(next);
            setError('');
          }
        })
        .catch(err => {
          if (!cancelled) {
            setError(err instanceof Error ? err.message : String(err));
          }
        });
    };
    refresh();
    const timer = window.setInterval(refresh, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [loadRuns]);

  async function onRowClick(row: RunRow | undefined) {
    if (!row) {
      return;
    }
    setSelected(row);
    setDetailError('');
    try {
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(`${base}/repave/api/v2/runs/${row.runId}`);
      const text = await response.text();
      let body: unknown = {};
      try {
        body = text ? JSON.parse(text) : {};
      } catch {
        body = { detail: text };
      }
      if (!response.ok) {
        const detail =
          body && typeof body === 'object' && 'detail' in body
            ? String((body as { detail: unknown }).detail)
            : text;
        throw new Error(detail || `GET /api/v2/runs/${row.runId} returned ${response.status}`);
      }
      const parsed = parseRunDetail(body);
      if (parsed) {
        setSelected(parsed);
      }
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <Page themeId="tool">
      <Header
        title="Runs"
        subtitle="Recent jobs from the durability queue. This list refreshes while the page is open."
      />
      <Content>
        {error ? <p>{error}</p> : null}
        {rows === undefined && !error ? <Progress /> : null}
        {rows ? (
          <Table
            options={{ paging: rows.length > 20, search: true, padding: 'dense' }}
            columns={COLUMNS}
            data={rows}
            onRowClick={(_event, row) => {
              void onRowClick(row);
            }}
            emptyContent={<p>No async runs yet.</p>}
          />
        ) : null}
        {selected ? (
          <InfoCard title={`Run ${selected.runId}`}>
            <p>Status: {selected.status}</p>
            <p>Mode: {selected.mode}</p>
            {selected.kind ? <p>Kind: {selected.kind}</p> : null}
            {selected.blueprint ? <p>Blueprint: {selected.blueprint}</p> : null}
            {selected.gatesOutcome ? <p>Gates: {selected.gatesOutcome}</p> : null}
            {selected.error ? <p>{selected.error}</p> : null}
            {detailError ? <p>{detailError}</p> : null}
          </InfoCard>
        ) : null}
      </Content>
    </Page>
  );
}
