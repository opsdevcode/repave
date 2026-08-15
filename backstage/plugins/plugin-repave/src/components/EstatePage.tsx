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

export type EstateTileRow = {
  repoUrl: string;
  title: string;
  owner: string;
  blueprintName: string;
  blueprintLabel: string;
  operatorPhase: string;
  statusLabel: string;
  freshness: string;
  freshnessDetail: string;
  sparkline: string;
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

export function sparklineLabel(values: unknown): string {
  if (!Array.isArray(values)) {
    return '';
  }
  return values
    .map(item => {
      const value = Number(item);
      if (value === 1) {
        return '+';
      }
      if (value === 0) {
        return '-';
      }
      return '.';
    })
    .join('');
}

export function rowsFromTiles(items: unknown[]): EstateTileRow[] {
  return items
    .filter(item => item && typeof item === 'object')
    .map(item => {
      const record = item as Record<string, unknown>;
      const repoUrl = String(record.repo_url ?? '');
      return {
        repoUrl,
        title: String(record.title ?? repoUrl),
        owner: String(record.owner ?? ''),
        blueprintName: String(record.blueprint_name ?? ''),
        blueprintLabel: String(record.blueprint_label ?? ''),
        operatorPhase: String(record.operator_phase ?? ''),
        statusLabel: String(record.status_label ?? ''),
        freshness: String(record.freshness ?? ''),
        freshnessDetail: String(record.freshness_detail ?? ''),
        sparkline: sparklineLabel(record.sparkline),
      };
    })
    .filter(row => row.repoUrl)
    .sort((left, right) => left.title.localeCompare(right.title));
}

export function parseEstatePayload(body: unknown): { count: number; rows: EstateTileRow[] } {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const items = Array.isArray(record.tiles) ? record.tiles : [];
  const rows = rowsFromTiles(items);
  return { count: Number(record.count ?? rows.length), rows };
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

const COLUMNS: TableColumn<EstateTileRow>[] = [
  { title: 'Repo', field: 'title' },
  { title: 'Owner', field: 'owner' },
  { title: 'Blueprint', field: 'blueprintLabel' },
  { title: 'Freshness', field: 'freshness' },
  { title: 'Status', field: 'statusLabel' },
  { title: 'Operator', field: 'operatorPhase' },
  { title: 'Audit', field: 'sparkline' },
  { title: 'Detail', field: 'freshnessDetail' },
];

export function EstatePage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [rows, setRows] = useState<EstateTileRow[] | undefined>();
  const [error, setError] = useState('');

  const loadEstate = useCallback(async () => {
    const base = await discoveryApi.getBaseUrl('proxy');
    const response = await fetchApi.fetch(`${base}/repave/api/v2/estate`);
    const text = await response.text();
    const body = parseJsonBody(text);
    if (!response.ok) {
      throw new Error(
        parseApiDetail(body, `GET /api/v2/estate returned ${response.status}`),
      );
    }
    return parseEstatePayload(body).rows;
  }, [discoveryApi, fetchApi]);

  useEffect(() => {
    let cancelled = false;
    loadEstate()
      .then(next => {
        if (!cancelled) {
          setRows(next);
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
  }, [loadEstate]);

  return (
    <Page themeId="tool">
      <Header
        title="Estate"
        subtitle="Fleet freshness and audit sparklines from GET /api/v2/estate."
      />
      <Content>
        {error ? <p>{error}</p> : null}
        {rows === undefined && !error ? <Progress /> : null}
        {rows ? (
          <Table
            options={{ paging: rows.length > 20, search: true, padding: 'dense' }}
            columns={COLUMNS}
            data={rows}
            emptyContent={<p>No estate tiles yet.</p>}
          />
        ) : null}
      </Content>
    </Page>
  );
}
