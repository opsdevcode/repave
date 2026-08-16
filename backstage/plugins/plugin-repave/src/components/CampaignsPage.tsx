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
import Button from '@material-ui/core/Button';

export type CampaignRow = {
  name: string;
  namespace: string;
  phase: string;
  paused: boolean;
  openPrCount: number;
  outOfDateCount: number;
  blueprintName: string;
};

export type RemediationRow = {
  repoUrl: string;
  phase: string;
  pullRequestUrl: string;
};

export type CampaignsView = {
  operatorEnabled: boolean;
  gitopsNamespace: string;
  updatedAt: string;
  campaigns: CampaignRow[];
  remediation: RemediationRow[];
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

export function parseCampaignsPayload(body: unknown): CampaignsView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const snapshot =
    record.snapshot && typeof record.snapshot === 'object'
      ? (record.snapshot as Record<string, unknown>)
      : {};
  const campaigns = Array.isArray(snapshot.campaigns)
    ? snapshot.campaigns
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const row = item as Record<string, unknown>;
          return {
            name: String(row.name ?? ''),
            namespace: String(row.namespace ?? 'default'),
            phase: String(row.phase ?? ''),
            paused: Boolean(row.paused),
            openPrCount: Number(row.open_pr_count ?? 0),
            outOfDateCount: Number(row.out_of_date_count ?? 0),
            blueprintName: String(row.blueprint_name ?? ''),
          };
        })
        .filter(row => row.name)
    : [];
  const remediation = Array.isArray(record.remediation_queue)
    ? record.remediation_queue
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const row = item as Record<string, unknown>;
          return {
            repoUrl: String(row.repo_url ?? ''),
            phase: String(row.phase ?? ''),
            pullRequestUrl: String(row.remediation_pr_url ?? ''),
          };
        })
        .filter(row => row.repoUrl)
    : [];
  return {
    operatorEnabled: Boolean(record.operator_status_enabled),
    gitopsNamespace: String(record.gitops_namespace ?? ''),
    updatedAt: String(snapshot.updated_at ?? ''),
    campaigns,
    remediation,
  };
}

export function campaignPausedPath(namespace: string, name: string): string {
  return `/platform/campaigns/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}/paused`;
}

export function buildCampaignPausedRequest(paused: boolean): { paused: boolean } {
  return { paused };
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

const CAMPAIGN_COLUMNS: TableColumn<CampaignRow>[] = [
  { title: 'Name', field: 'name' },
  { title: 'Namespace', field: 'namespace' },
  { title: 'Phase', field: 'phase' },
  { title: 'Paused', field: 'paused' },
  { title: 'Open PRs', field: 'openPrCount' },
  { title: 'Out of date', field: 'outOfDateCount' },
];

const REMEDIATION_COLUMNS: TableColumn<RemediationRow>[] = [
  { title: 'Repo', field: 'repoUrl' },
  { title: 'Phase', field: 'phase' },
  { title: 'PR', field: 'pullRequestUrl' },
];

export function CampaignsPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [view, setView] = useState<CampaignsView | undefined>();
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const base = await discoveryApi.getBaseUrl('proxy');
    const response = await fetchApi.fetch(`${base}/repave/api/v2/platform/campaigns`);
    const body = parseJsonBody(await response.text());
    if (!response.ok) {
      throw new Error(
        parseApiDetail(body, `GET /api/v2/platform/campaigns returned ${response.status}`),
      );
    }
    return parseCampaignsPayload(body);
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

  const setPaused = async (row: CampaignRow, paused: boolean) => {
    setBusy(true);
    setNotice('');
    try {
      const base = await discoveryApi.getBaseUrl('proxy');
      const path = campaignPausedPath(row.namespace, row.name);
      const response = await fetchApi.fetch(`${base}/repave/api/v2${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildCampaignPausedRequest(paused)),
      });
      const body = parseJsonBody(await response.text());
      if (!response.ok) {
        throw new Error(parseApiDetail(body, `POST /api/v2${path} returned ${response.status}`));
      }
      setNotice(`${paused ? 'Paused' : 'Resumed'} ${row.namespace}/${row.name}.`);
      setView(await load());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Page themeId="tool">
      <Header
        title="Campaigns"
        subtitle="Operator upgrade campaigns from GET /api/v2/platform/campaigns."
      />
      <Content>
        {error ? <p>{error}</p> : null}
        {notice ? <p>{notice}</p> : null}
        {view === undefined && !error ? <Progress /> : null}
        {view ? (
          <>
            <InfoCard title="Snapshot">
              <StructuredMetadataTable
                metadata={{
                  Operator: view.operatorEnabled ? 'enabled' : 'unset',
                  Namespace: view.gitopsNamespace || 'n/a',
                  Updated: view.updatedAt || 'n/a',
                }}
              />
            </InfoCard>
            <Table
              title="Campaigns"
              options={{ paging: view.campaigns.length > 10, search: false, padding: 'dense' }}
              columns={CAMPAIGN_COLUMNS}
              data={view.campaigns}
              emptyContent={<p>No campaigns in the operator snapshot.</p>}
              actions={[
                row => ({
                  icon: () => <Button size="small">{row.paused ? 'Resume' : 'Pause'}</Button>,
                  tooltip: row.paused ? 'Resume' : 'Pause',
                  disabled: busy,
                  onClick: () => void setPaused(row, !row.paused),
                }),
              ]}
            />
            <Table
              title="Remediation queue"
              options={{ paging: view.remediation.length > 10, search: false, padding: 'dense' }}
              columns={REMEDIATION_COLUMNS}
              data={view.remediation}
              emptyContent={<p>No open remediation PRs.</p>}
            />
          </>
        ) : null}
      </Content>
    </Page>
  );
}
