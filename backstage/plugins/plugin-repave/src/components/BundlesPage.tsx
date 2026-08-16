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
import { queryParam } from './queryParam';
import { scaffolderHref } from './GeneratePage';

export type BundleRow = {
  name: string;
  version: string;
  description: string;
  memberCount: number;
};

export type BundleMember = {
  id: string;
  blueprint: string;
};

export type BundleDetail = {
  name: string;
  version: string;
  description: string;
  members: BundleMember[];
  edges: { source: string; target: string; label: string }[];
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

export function parseBundlesPayload(body: unknown): BundleRow[] {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const items = Array.isArray(record.bundles) ? record.bundles : [];
  return items
    .filter(item => item && typeof item === 'object')
    .map(item => {
      const bundle = item as Record<string, unknown>;
      const members = Array.isArray(bundle.members) ? bundle.members : [];
      return {
        name: String(bundle.name ?? ''),
        version: String(bundle.version ?? ''),
        description: String(bundle.description ?? ''),
        memberCount: members.length,
      };
    })
    .filter(row => row.name);
}

export function parseBundleDetail(body: unknown): BundleDetail | undefined {
  if (!body || typeof body !== 'object') {
    return undefined;
  }
  const record = body as Record<string, unknown>;
  const name = String(record.name ?? '');
  if (!name) {
    return undefined;
  }
  const members = Array.isArray(record.members)
    ? record.members
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const member = item as Record<string, unknown>;
          return {
            id: String(member.id ?? ''),
            blueprint: String(member.blueprint ?? ''),
          };
        })
        .filter(member => member.id)
    : [];
  const topology =
    record.topology && typeof record.topology === 'object'
      ? (record.topology as Record<string, unknown>)
      : {};
  const edges = Array.isArray(topology.edges)
    ? topology.edges
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const edge = item as Record<string, unknown>;
          return {
            source: String(edge.source ?? ''),
            target: String(edge.target ?? ''),
            label: String(edge.label ?? ''),
          };
        })
        .filter(edge => edge.source && edge.target)
    : [];
  return {
    name,
    version: String(record.version ?? ''),
    description: String(record.description ?? ''),
    members,
    edges,
  };
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

const COLUMNS: TableColumn<BundleRow>[] = [
  { title: 'Bundle', field: 'name' },
  { title: 'Version', field: 'version' },
  { title: 'Members', field: 'memberCount' },
  { title: 'Description', field: 'description' },
];

const MEMBER_COLUMNS: TableColumn<BundleMember>[] = [
  { title: 'Member', field: 'id' },
  { title: 'Blueprint', field: 'blueprint' },
];

export function BundlesPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [rows, setRows] = useState<BundleRow[] | undefined>();
  const [selected, setSelected] = useState<BundleDetail | undefined>();
  const [error, setError] = useState('');
  const [detailError, setDetailError] = useState('');

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(`${base}/repave/api/v2/bundles`);
      const text = await response.text();
      const body = parseJsonBody(text);
      if (!response.ok) {
        throw new Error(parseApiDetail(body, `GET /api/v2/bundles returned ${response.status}`));
      }
      return parseBundlesPayload(body);
    };
    load()
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
  }, [discoveryApi, fetchApi]);

  useEffect(() => {
    const name = queryParam(window.location.search, 'name');
    let cancelled = false;
    if (!name) {
      return () => {
        cancelled = true;
      };
    }
    const load = async () => {
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(
        `${base}/repave/api/v2/bundles/${encodeURIComponent(name)}`,
      );
      const text = await response.text();
      const body = parseJsonBody(text);
      if (!response.ok) {
        throw new Error(
          parseApiDetail(body, `GET /api/v2/bundles/${name} returned ${response.status}`),
        );
      }
      return parseBundleDetail(body);
    };
    load()
      .then(next => {
        if (!cancelled) {
          setSelected(next);
          setDetailError('');
        }
      })
      .catch(err => {
        if (!cancelled) {
          setDetailError(err instanceof Error ? err.message : String(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [discoveryApi, fetchApi]);

  async function onRowClick(row: BundleRow | undefined) {
    if (!row) {
      return;
    }
    setDetailError('');
    try {
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(
        `${base}/repave/api/v2/bundles/${encodeURIComponent(row.name)}`,
      );
      const text = await response.text();
      const body = parseJsonBody(text);
      if (!response.ok) {
        throw new Error(
          parseApiDetail(body, `GET /api/v2/bundles/${row.name} returned ${response.status}`),
        );
      }
      setSelected(parseBundleDetail(body));
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <Page themeId="tool">
      <Header
        title="Bundles"
        subtitle="Multi-blueprint golden paths. Submit still goes through Scaffolder."
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
            emptyContent={<p>No bundles in the catalog.</p>}
          />
        ) : null}
        {detailError ? <p>{detailError}</p> : null}
        {selected ? (
          <InfoCard title={`${selected.name} ${selected.version}`.trim()}>
            <p>{selected.description}</p>
            <p>
              Create a bundle from <Link to={scaffolderHref()}>Scaffolder</Link> (
              <code>POST /api/v2/generate</code>).
            </p>
            <Table
              options={{ paging: false, search: false, padding: 'dense' }}
              columns={MEMBER_COLUMNS}
              data={selected.members}
              emptyContent={<p>No members.</p>}
            />
            {selected.edges.length ? (
              <p>
                Topology:{' '}
                {selected.edges.map(edge => `${edge.source} → ${edge.target}`).join(', ')}
              </p>
            ) : null}
          </InfoCard>
        ) : null}
      </Content>
    </Page>
  );
}
