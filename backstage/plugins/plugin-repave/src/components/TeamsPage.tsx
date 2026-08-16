import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  Content,
  Header,
  InfoCard,
  Link,
  Page,
  Progress,
  Table,
  type TableColumn,
} from '@backstage/core-components';
import { discoveryApiRef, fetchApiRef, useApi } from '@backstage/core-plugin-api';
import Button from '@material-ui/core/Button';
import TextField from '@material-ui/core/TextField';
import { queryParam } from './queryParam';

export type TeamEntity = {
  entityId: string;
  displayName: string;
  owner: string;
  teamSlug: string;
  maturityLevel: number;
  maturityLabel: string;
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

export function teamsPath(slug: string): string {
  const value = slug.trim();
  return value ? `/teams?slug=${encodeURIComponent(value)}` : '/teams';
}

export function parseTeamEntities(body: unknown): TeamEntity[] {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const items = Array.isArray(record.entities) ? record.entities : [];
  return items
    .filter(item => item && typeof item === 'object')
    .map(item => {
      const entity = item as Record<string, unknown>;
      const maturity =
        entity.maturity && typeof entity.maturity === 'object'
          ? (entity.maturity as Record<string, unknown>)
          : {};
      return {
        entityId: String(entity.entity_id ?? ''),
        displayName: String(entity.display_name ?? entity.entity_id ?? ''),
        owner: String(entity.owner ?? ''),
        teamSlug: String(entity.team_slug ?? ''),
        maturityLevel: Number(maturity.level ?? 0),
        maturityLabel: String(maturity.label ?? ''),
      };
    })
    .filter(row => row.entityId);
}

export function averageMaturity(rows: TeamEntity[]): string {
  const scored = rows.filter(row => Number.isFinite(row.maturityLevel) && row.maturityLevel > 0);
  if (!scored.length) {
    return 'n/a';
  }
  const total = scored.reduce((sum, row) => sum + row.maturityLevel, 0);
  return (Math.round((total / scored.length) * 10) / 10).toFixed(1);
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

const COLUMNS: TableColumn<TeamEntity>[] = [
  {
    title: 'Entity',
    field: 'displayName',
    render: row => (
      <Link to={`/services?entity=${encodeURIComponent(row.entityId)}`}>{row.displayName}</Link>
    ),
  },
  { title: 'Owner', field: 'owner' },
  { title: 'Team', field: 'teamSlug' },
  { title: 'Maturity', field: 'maturityLabel' },
];

export function TeamsPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [slug, setSlug] = useState(() => queryParam(window.location.search, 'slug'));
  const [rows, setRows] = useState<TeamEntity[] | undefined>();
  const [error, setError] = useState('');

  const loadTeam = useCallback(
    async (nextSlug: string) => {
      if (!nextSlug) {
        return [];
      }
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(
        `${base}/repave/api/v2/catalog/entities?team=${encodeURIComponent(nextSlug)}`,
      );
      const text = await response.text();
      const body = parseJsonBody(text);
      if (!response.ok) {
        throw new Error(
          parseApiDetail(body, `GET /api/v2/catalog/entities returned ${response.status}`),
        );
      }
      return parseTeamEntities(body);
    },
    [discoveryApi, fetchApi],
  );

  useEffect(() => {
    let cancelled = false;
    if (!slug) {
      setRows([]);
      return () => {
        cancelled = true;
      };
    }
    loadTeam(slug)
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
    return () => {
      cancelled = true;
    };
  }, [loadTeam, slug]);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const next = slug.trim();
    setSlug(next);
    window.history.replaceState(null, '', teamsPath(next));
  }

  return (
    <Page themeId="tool">
      <Header title="Teams" subtitle="Catalog entities for a team slug." />
      <Content>
        <form onSubmit={onSubmit}>
          <TextField
            label="Team slug"
            value={slug}
            onChange={event => setSlug(event.target.value)}
            helperText="Uses GET /api/v2/catalog/entities?team="
          />
          <Button color="primary" type="submit">
            Load team
          </Button>
        </form>
        {error ? <p>{error}</p> : null}
        {rows === undefined && slug && !error ? <Progress /> : null}
        {rows ? (
          <>
            <InfoCard title={slug || 'Pick a team'}>
              <p>
                {rows.length} entities · average maturity {averageMaturity(rows)}
              </p>
            </InfoCard>
            <Table
              options={{ paging: rows.length > 20, search: true, padding: 'dense' }}
              columns={COLUMNS}
              data={rows}
              emptyContent={<p>Enter a team slug to list its catalog entities.</p>}
            />
          </>
        ) : null}
      </Content>
    </Page>
  );
}
