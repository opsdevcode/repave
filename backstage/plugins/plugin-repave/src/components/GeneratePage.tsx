import { useEffect, useState } from 'react';
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

export type BlueprintRow = {
  name: string;
  version: string;
  description: string;
  artifactType: string;
  family: string;
  familyTitle: string;
};

export type BlueprintFamily = {
  family: string;
  title: string;
  subtitle: string;
  count: number;
};

export type BlueprintCatalog = {
  families: BlueprintFamily[];
  rows: BlueprintRow[];
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

export function scaffolderHref(): string {
  return '/create';
}

export function parseBlueprintCatalog(body: unknown): BlueprintCatalog {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const groups = Array.isArray(record.groups) ? record.groups : [];
  const families: BlueprintFamily[] = [];
  const rows: BlueprintRow[] = [];
  for (const item of groups) {
    if (!item || typeof item !== 'object') {
      continue;
    }
    const group = item as Record<string, unknown>;
    const family = String(group.family ?? '');
    const title = String(group.title ?? family);
    const blueprints = Array.isArray(group.blueprints) ? group.blueprints : [];
    if (!family) {
      continue;
    }
    const start = rows.length;
    for (const raw of blueprints) {
      if (!raw || typeof raw !== 'object') {
        continue;
      }
      const blueprint = raw as Record<string, unknown>;
      const name = String(blueprint.name ?? '');
      if (!name) {
        continue;
      }
      rows.push({
        name,
        version: String(blueprint.version ?? ''),
        description: String(blueprint.description ?? ''),
        artifactType: String(blueprint.artifact_type ?? ''),
        family,
        familyTitle: title,
      });
    }
    families.push({
      family,
      title,
      subtitle: String(group.subtitle ?? ''),
      count: rows.length - start,
    });
  }
  return { families, rows };
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

const COLUMNS: TableColumn<BlueprintRow>[] = [
  { title: 'Blueprint', field: 'name' },
  { title: 'Family', field: 'familyTitle' },
  { title: 'Type', field: 'artifactType' },
  { title: 'Version', field: 'version' },
  { title: 'Description', field: 'description' },
];

export function GeneratePage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [catalog, setCatalog] = useState<BlueprintCatalog | undefined>();
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(`${base}/repave/api/v2/catalog/blueprints`);
      const text = await response.text();
      const body = parseJsonBody(text);
      if (!response.ok) {
        throw new Error(
          parseApiDetail(body, `GET /api/v2/catalog/blueprints returned ${response.status}`),
        );
      }
      return parseBlueprintCatalog(body);
    };
    load()
      .then(next => {
        if (!cancelled) {
          setCatalog(next);
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
  }, [discoveryApi, fetchApi]);

  return (
    <Page themeId="tool">
      <Header
        title="Generate"
        subtitle="Governed blueprints grouped by family. Create a repo from Scaffolder."
      />
      <Content>
        {error ? <p>{error}</p> : null}
        {catalog === undefined && !error ? <Progress /> : null}
        {catalog ? (
          <>
            <InfoCard title="Start a generate">
              <p>
                This page lists the catalog. Submit still goes through Scaffolder (
                <Link to={scaffolderHref()}>Create</Link>) which posts{' '}
                <code>POST /api/v2/generate</code>.
              </p>
            </InfoCard>
            {catalog.families.map(family => (
              <InfoCard key={family.family} title={`${family.title} (${family.count})`}>
                <p>{family.subtitle}</p>
              </InfoCard>
            ))}
            <Table
              options={{ paging: catalog.rows.length > 20, search: true, padding: 'dense' }}
              columns={COLUMNS}
              data={catalog.rows}
              emptyContent={<p>No blueprints in the catalog.</p>}
            />
          </>
        ) : null}
      </Content>
    </Page>
  );
}
