import { useCallback, useEffect, useState } from 'react';
import {
  Content,
  Header,
  InfoCard,
  Page,
  Progress,
  Table,
  type TableColumn,
} from '@backstage/core-components';
import { discoveryApiRef, fetchApiRef, useApi } from '@backstage/core-plugin-api';
import Button from '@material-ui/core/Button';

export type BehindRepo = {
  repoUrl: string;
  owner: string;
  pinFields: string;
};

export type StandardsRow = {
  blueprintName: string;
  catalogVersion: string;
  governed: number;
  current: number;
  behind: number;
  repoUrls: string[];
  behindRepos: BehindRepo[];
};

export type StandardsView = {
  fleetEnabled: boolean;
  rows: StandardsRow[];
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

export function parseStandardsPayload(body: unknown): StandardsView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const rows = Array.isArray(record.summaries)
    ? record.summaries
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const row = item as Record<string, unknown>;
          const behindRepos = Array.isArray(row.behind_repos)
            ? row.behind_repos
                .filter(repo => repo && typeof repo === 'object')
                .map(repo => {
                  const entry = repo as Record<string, unknown>;
                  const fields = Array.isArray(entry.pin_fields)
                    ? entry.pin_fields.map(field => String(field)).filter(Boolean)
                    : [];
                  return {
                    repoUrl: String(entry.repo_url ?? ''),
                    owner: String(entry.owner ?? ''),
                    pinFields: fields.join(', '),
                  };
                })
                .filter(repo => repo.repoUrl)
            : [];
          return {
            blueprintName: String(row.blueprint_name ?? ''),
            catalogVersion: String(row.catalog_version ?? ''),
            governed: Number(row.governed_count ?? 0),
            current: Number(row.current_count ?? 0),
            behind: Number(row.behind_count ?? 0),
            repoUrls: behindRepos.map(repo => repo.repoUrl),
            behindRepos,
          };
        })
        .filter(row => row.blueprintName)
    : [];
  return {
    fleetEnabled: Boolean(record.fleet_enabled),
    rows,
  };
}

export function buildDriftConfirmRequest(repoUrls: string[]): {
  ok: true;
  body: Record<string, unknown>;
} {
  return {
    ok: true,
    body: { kind: 'fleet_drift_confirm', repo_urls: repoUrls },
  };
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

const COLUMNS: TableColumn<StandardsRow>[] = [
  { title: 'Blueprint', field: 'blueprintName' },
  { title: 'Catalog', field: 'catalogVersion' },
  { title: 'Governed', field: 'governed' },
  { title: 'Current', field: 'current' },
  { title: 'Behind', field: 'behind' },
];

export function StandardsPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [view, setView] = useState<StandardsView | undefined>();
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const base = await discoveryApi.getBaseUrl('proxy');
    const response = await fetchApi.fetch(`${base}/repave/api/v2/platform/standards`);
    const body = parseJsonBody(await response.text());
    if (!response.ok) {
      throw new Error(
        parseApiDetail(body, `GET /api/v2/platform/standards returned ${response.status}`),
      );
    }
    return parseStandardsPayload(body);
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

  const confirmDrift = async (row: StandardsRow) => {
    setBusy(true);
    setNotice('');
    try {
      const request = buildDriftConfirmRequest(row.repoUrls);
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(`${base}/repave/api/v2/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request.body),
      });
      const body = parseJsonBody(await response.text());
      if (!response.ok) {
        throw new Error(parseApiDetail(body, `POST /api/v2/runs returned ${response.status}`));
      }
      setNotice(
        `Queued drift confirm for ${row.blueprintName} (${String(
          (body as { run_id?: unknown }).run_id ?? '',
        )}).`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Page themeId="tool">
      <Header
        title="Standards"
        subtitle="Fleet pin drift from GET /api/v2/platform/standards."
      />
      <Content>
        {error ? <p>{error}</p> : null}
        {notice ? <p>{notice}</p> : null}
        {view === undefined && !error ? <Progress /> : null}
        {view && !view.fleetEnabled ? (
          <InfoCard title="Fleet unset">
            <p>Set fleet.file or REPAVE_FLEET_FILE to estimate standards drift.</p>
          </InfoCard>
        ) : null}
        {view?.fleetEnabled ? (
          <Table
            title="Blueprint drift"
            options={{ paging: view.rows.length > 10, search: false, padding: 'dense' }}
            columns={COLUMNS}
            data={view.rows}
            emptyContent={<p>No governed blueprints.</p>}
            detailPanel={({ rowData }) =>
              rowData.behindRepos.length ? (
                <ul>
                  {rowData.behindRepos.map(repo => (
                    <li key={repo.repoUrl}>
                      <code>{repo.repoUrl}</code>
                      {repo.pinFields ? ` (${repo.pinFields})` : ''}
                    </li>
                  ))}
                </ul>
              ) : (
                <p>No behind repos.</p>
              )
            }
            actions={[
              row => ({
                icon: () => <Button size="small">Confirm drift</Button>,
                tooltip: 'Confirm drift',
                disabled: busy || row.repoUrls.length === 0,
                onClick: () => void confirmDrift(row),
              }),
            ]}
          />
        ) : null}
      </Content>
    </Page>
  );
}
