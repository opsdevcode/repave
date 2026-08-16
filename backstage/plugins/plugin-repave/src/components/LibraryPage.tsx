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

export type LibraryFamily = {
  family: string;
  title: string;
  subtitle: string;
  count: number;
};

export type LibraryEntity = {
  entityId: string;
  displayName: string;
  owner: string;
  blueprint: string;
  maturity: string;
};

export type LibraryView = {
  entityCount: number;
  owner: string;
  family: string;
  overall: string;
  families: LibraryFamily[];
  entities: LibraryEntity[];
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

export function libraryPath(input: { family?: string; owner?: string }): string {
  const params = new URLSearchParams();
  if (input.family?.trim()) {
    params.set('family', input.family.trim());
  }
  if (input.owner?.trim()) {
    params.set('owner', input.owner.trim());
  }
  const query = params.toString();
  return query ? `/library?${query}` : '/library';
}

function entityFromRecord(record: Record<string, unknown>): LibraryEntity | undefined {
  const entityId = String(record.entity_id ?? '');
  if (!entityId) {
    return undefined;
  }
  const maturity =
    record.maturity && typeof record.maturity === 'object'
      ? (record.maturity as Record<string, unknown>)
      : {};
  const label = String(maturity.label ?? '');
  const level = maturity.level === undefined || maturity.level === null ? '' : String(maturity.level);
  return {
    entityId,
    displayName: String(record.display_name ?? entityId),
    owner: String(record.owner ?? ''),
    blueprint: String(record.blueprint_name ?? ''),
    maturity: label || level,
  };
}

export function parseLibraryPayload(body: unknown): LibraryView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const scorecard =
    record.scorecard && typeof record.scorecard === 'object'
      ? (record.scorecard as Record<string, unknown>)
      : {};
  const groups = Array.isArray(record.groups) ? record.groups : [];
  const families: LibraryFamily[] = [];
  const entities: LibraryEntity[] = [];
  for (const item of groups) {
    if (!item || typeof item !== 'object') {
      continue;
    }
    const group = item as Record<string, unknown>;
    const family = String(group.family ?? '');
    if (!family) {
      continue;
    }
    const members = Array.isArray(group.entities) ? group.entities : [];
    families.push({
      family,
      title: String(group.title ?? family),
      subtitle: String(group.subtitle ?? ''),
      count: Number(group.count ?? members.length),
    });
    for (const raw of members) {
      if (!raw || typeof raw !== 'object') {
        continue;
      }
      const parsed = entityFromRecord(raw as Record<string, unknown>);
      if (parsed) {
        entities.push(parsed);
      }
    }
  }
  return {
    entityCount: Number(record.entity_count ?? entities.length),
    owner: String(record.owner ?? ''),
    family: String(record.family ?? ''),
    overall: String(scorecard.overall ?? ''),
    families,
    entities,
  };
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

const COLUMNS: TableColumn<LibraryEntity>[] = [
  {
    title: 'Entity',
    field: 'displayName',
    render: row => (
      <Link to={`/services?entity=${encodeURIComponent(row.entityId)}`}>{row.displayName}</Link>
    ),
  },
  { title: 'Owner', field: 'owner' },
  { title: 'Blueprint', field: 'blueprint' },
  { title: 'Maturity', field: 'maturity' },
];

export function LibraryPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [view, setView] = useState<LibraryView | undefined>();
  const [error, setError] = useState('');
  const [owner, setOwner] = useState(() => queryParam(window.location.search, 'owner'));
  const [family, setFamily] = useState(() => queryParam(window.location.search, 'family'));

  const loadLibrary = useCallback(
    async (nextFamily: string, nextOwner: string) => {
      const params = new URLSearchParams();
      if (nextFamily) {
        params.set('family', nextFamily);
      }
      if (nextOwner) {
        params.set('owner', nextOwner);
      }
      const query = params.toString();
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(
        `${base}/repave/api/v2/library${query ? `?${query}` : ''}`,
      );
      const text = await response.text();
      const body = parseJsonBody(text);
      if (!response.ok) {
        throw new Error(parseApiDetail(body, `GET /api/v2/library returned ${response.status}`));
      }
      return parseLibraryPayload(body);
    },
    [discoveryApi, fetchApi],
  );

  useEffect(() => {
    let cancelled = false;
    loadLibrary(family, owner)
      .then(next => {
        if (!cancelled) {
          setView(next);
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
  }, [family, loadLibrary, owner]);

  function onFilter(event: FormEvent) {
    event.preventDefault();
    const nextOwner = owner.trim();
    setOwner(nextOwner);
    window.history.replaceState(null, '', libraryPath({ family, owner: nextOwner }));
  }

  function onFamily(next: string) {
    const value = next === family ? '' : next;
    setFamily(value);
    window.history.replaceState(null, '', libraryPath({ family: value, owner }));
  }

  return (
    <Page themeId="tool">
      <Header title="Library" subtitle="Governed artifacts grouped by family." />
      <Content>
        <form onSubmit={onFilter}>
          <TextField
            label="Owner"
            value={owner}
            onChange={event => setOwner(event.target.value)}
            helperText="Substring match on entity.owner"
          />
          <Button color="primary" type="submit">
            Filter
          </Button>
        </form>
        {error ? <p>{error}</p> : null}
        {view === undefined && !error ? <Progress /> : null}
        {view ? (
          <>
            <InfoCard title={`${view.entityCount} entities`}>
              <p>
                Scorecard: {view.overall || 'n/a'}
                {view.family ? ` · family ${view.family}` : ''}
                {view.owner ? ` · owner ${view.owner}` : ''}
              </p>
            </InfoCard>
            {view.families.map(item => (
              <InfoCard key={item.family} title={`${item.title} (${item.count})`}>
                <p>{item.subtitle}</p>
                <Button
                  color="primary"
                  onClick={() => {
                    onFamily(item.family);
                  }}
                >
                  {family === item.family ? 'Show all families' : 'Show this family'}
                </Button>
              </InfoCard>
            ))}
            <Table
              options={{ paging: view.entities.length > 20, search: true, padding: 'dense' }}
              columns={COLUMNS}
              data={view.entities}
              emptyContent={<p>No entities in this library view.</p>}
            />
          </>
        ) : null}
      </Content>
    </Page>
  );
}
