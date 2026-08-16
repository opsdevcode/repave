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

export type MaturityLevelRow = {
  level: number;
  count: number;
};

export type MaturityEntityRow = {
  entityId: string;
  displayName: string;
  owner: string;
  maturityLevel: number;
  maturityLabel: string;
};

export type MaturityView = {
  catalogEnabled: boolean;
  entityCount: number;
  averageLevel: string;
  byLevel: MaturityLevelRow[];
  bottom: MaturityEntityRow[];
};

export type InitiativeRow = {
  id: string;
  title: string;
  owningTeam: string;
  targetLevel: number;
  passed: number;
  total: number;
  ratio: string;
  overdue: boolean;
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

export function parseMaturityPayload(body: unknown): MaturityView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const byLevel = Array.isArray(record.by_level)
    ? record.by_level
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const row = item as Record<string, unknown>;
          return { level: Number(row.level ?? 0), count: Number(row.count ?? 0) };
        })
    : [];
  const bottom = Array.isArray(record.bottom_entities)
    ? record.bottom_entities
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const row = item as Record<string, unknown>;
          return {
            entityId: String(row.entity_id ?? ''),
            displayName: String(row.display_name ?? row.entity_id ?? ''),
            owner: String(row.owner ?? ''),
            maturityLevel: Number(row.maturity_level ?? 0),
            maturityLabel: String(row.maturity_label ?? ''),
          };
        })
        .filter(row => row.entityId)
    : [];
  const average = Number(record.average_level ?? 0);
  return {
    catalogEnabled: Boolean(record.catalog_enabled),
    entityCount: Number(record.entity_count ?? 0),
    averageLevel: Number.isFinite(average) ? average.toFixed(1) : '0.0',
    byLevel,
    bottom,
  };
}

export function rowsFromInitiatives(items: unknown[]): InitiativeRow[] {
  return items
    .filter(item => item && typeof item === 'object')
    .map(item => {
      const record = item as Record<string, unknown>;
      const initiative =
        record.initiative && typeof record.initiative === 'object'
          ? (record.initiative as Record<string, unknown>)
          : {};
      return {
        id: String(initiative.id ?? ''),
        title: String(initiative.title ?? ''),
        owningTeam: String(initiative.owning_team ?? ''),
        targetLevel: Number(initiative.target_level ?? 0),
        passed: Number(record.passed ?? 0),
        total: Number(record.total ?? 0),
        ratio: formatRatio(record.ratio),
        overdue: Boolean(record.overdue),
      };
    })
    .filter(row => row.id);
}

export function parseInitiativesPayload(body: unknown): InitiativeRow[] {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const items = Array.isArray(record.initiatives) ? record.initiatives : [];
  return rowsFromInitiatives(items);
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

const LEVEL_COLUMNS: TableColumn<MaturityLevelRow>[] = [
  { title: 'Level', field: 'level' },
  { title: 'Services', field: 'count' },
];

const BOTTOM_COLUMNS: TableColumn<MaturityEntityRow>[] = [
  { title: 'Service', field: 'displayName' },
  { title: 'Owner', field: 'owner' },
  { title: 'Level', field: 'maturityLevel' },
  { title: 'Label', field: 'maturityLabel' },
];

const INITIATIVE_COLUMNS: TableColumn<InitiativeRow>[] = [
  { title: 'Initiative', field: 'title' },
  { title: 'Team', field: 'owningTeam' },
  { title: 'Target', field: 'targetLevel' },
  { title: 'Passed', field: 'passed' },
  { title: 'Total', field: 'total' },
  { title: 'Progress', field: 'ratio' },
  {
    title: 'Due',
    field: 'overdue',
    render: row => (row.overdue ? 'Overdue' : ''),
  },
];

export function MaturityPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [maturity, setMaturity] = useState<MaturityView | undefined>();
  const [initiatives, setInitiatives] = useState<InitiativeRow[] | undefined>();
  const [maturityError, setMaturityError] = useState('');
  const [initiativeError, setInitiativeError] = useState('');

  const load = useCallback(async () => {
    const base = await discoveryApi.getBaseUrl('proxy');
    const [maturityResponse, initiativeResponse] = await Promise.all([
      fetchApi.fetch(`${base}/repave/api/v2/platform/maturity`),
      fetchApi.fetch(`${base}/repave/api/v2/platform/initiatives`),
    ]);
    const maturityText = await maturityResponse.text();
    const initiativeText = await initiativeResponse.text();
    const maturityBody = parseJsonBody(maturityText);
    const initiativeBody = parseJsonBody(initiativeText);
    return {
      maturityOk: maturityResponse.ok,
      initiativeOk: initiativeResponse.ok,
      maturityBody,
      initiativeBody,
      maturityStatus: maturityResponse.status,
      initiativeStatus: initiativeResponse.status,
    };
  }, [discoveryApi, fetchApi]);

  useEffect(() => {
    let cancelled = false;
    load()
      .then(next => {
        if (cancelled) {
          return;
        }
        if (next.maturityOk) {
          setMaturity(parseMaturityPayload(next.maturityBody));
          setMaturityError('');
        } else {
          setMaturity(undefined);
          setMaturityError(
            parseApiDetail(
              next.maturityBody,
              `GET /api/v2/platform/maturity returned ${next.maturityStatus}`,
            ),
          );
        }
        if (next.initiativeOk) {
          setInitiatives(parseInitiativesPayload(next.initiativeBody));
          setInitiativeError('');
        } else {
          setInitiatives(undefined);
          setInitiativeError(
            parseApiDetail(
              next.initiativeBody,
              `GET /api/v2/platform/initiatives returned ${next.initiativeStatus}`,
            ),
          );
        }
      })
      .catch(err => {
        if (!cancelled) {
          setMaturityError(err instanceof Error ? err.message : String(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [load]);

  const loading = maturity === undefined && !maturityError && initiatives === undefined && !initiativeError;

  return (
    <Page themeId="tool">
      <Header
        title="Maturity"
        subtitle="Catalog maturity and initiative progress from /api/v2/platform. Create/update stays on the CLI or HTML portal."
      />
      <Content>
        {maturityError ? <p>{maturityError}</p> : null}
        {initiativeError ? <p>{initiativeError}</p> : null}
        {loading ? <Progress /> : null}
        {maturity ? (
          <>
            <InfoCard title="Distribution">
              <StructuredMetadataTable
                metadata={{
                  Services: String(maturity.entityCount),
                  'Average level': maturity.averageLevel,
                  Catalog: maturity.catalogEnabled ? 'On' : 'Off',
                }}
              />
            </InfoCard>
            <Table
              title="By level"
              options={{ paging: false, search: false, padding: 'dense' }}
              columns={LEVEL_COLUMNS}
              data={maturity.byLevel}
              emptyContent={<p>No maturity levels yet.</p>}
            />
            <Table
              title="Lowest services"
              options={{ paging: maturity.bottom.length > 10, search: true, padding: 'dense' }}
              columns={BOTTOM_COLUMNS}
              data={maturity.bottom}
              emptyContent={<p>No catalog entities yet.</p>}
            />
          </>
        ) : null}
        {initiatives ? (
          <Table
            title="Initiatives"
            options={{ paging: initiatives.length > 10, search: true, padding: 'dense' }}
            columns={INITIATIVE_COLUMNS}
            data={initiatives}
            emptyContent={<p>No active initiatives.</p>}
          />
        ) : null}
      </Content>
    </Page>
  );
}
