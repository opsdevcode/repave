import { useCallback, useEffect, useState, type FormEvent } from 'react';
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
import TextField from '@material-ui/core/TextField';

export type FleetRow = {
  repoUrl: string;
  displayName: string;
  family: string;
  blueprintName: string;
  blueprintVersion: string;
  owner: string;
  operatorPhase: string;
  operatorMessage: string;
  remediationPrUrl: string;
};

export function looksLikeGitRepoUrl(value: string): boolean {
  const trimmed = value.trim();
  return /^https?:\/\//i.test(trimmed) || /^git@/.test(trimmed);
}

export function rowsFromRepos(items: unknown[]): FleetRow[] {
  return items
    .filter(item => item && typeof item === 'object')
    .map(item => {
      const record = item as Record<string, unknown>;
      const repoUrl = String(record.repo_url ?? '');
      return {
        repoUrl,
        displayName: String(record.display_name ?? repoUrl),
        family: String(record.family ?? ''),
        blueprintName: String(record.blueprint_name ?? ''),
        blueprintVersion: String(record.blueprint_version ?? ''),
        owner: String(record.owner ?? ''),
        operatorPhase: String(record.operator_phase ?? ''),
        operatorMessage: String(record.operator_message ?? ''),
        remediationPrUrl: String(record.remediation_pr_url ?? ''),
      };
    })
    .filter(row => row.repoUrl)
    .sort((left, right) => left.displayName.localeCompare(right.displayName));
}

export function parseFleetPayload(body: unknown): { count: number; rows: FleetRow[] } {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const items = Array.isArray(record.repos) ? record.repos : [];
  const rows = rowsFromRepos(items);
  return { count: Number(record.count ?? rows.length), rows };
}

export function parseApiDetail(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = String((body as { detail: unknown }).detail).trim();
    if (detail) {
      return detail;
    }
  }
  return fallback;
}

export function buildRegisterRequest(input: {
  repoUrl: string;
  blueprintName: string;
  blueprintVersion: string;
  owner: string;
}): { ok: true; body: Record<string, string> } | { ok: false; error: string } {
  const repoUrl = input.repoUrl.trim();
  if (!looksLikeGitRepoUrl(repoUrl)) {
    return { ok: false, error: 'Repository URL must start with https:// or git@' };
  }
  const blueprintName = input.blueprintName.trim();
  if (!blueprintName) {
    return { ok: false, error: 'Blueprint name is required' };
  }
  const body: Record<string, string> = {
    repo_url: repoUrl,
    blueprint_name: blueprintName,
  };
  const blueprintVersion = input.blueprintVersion.trim();
  if (blueprintVersion) {
    body.blueprint_version = blueprintVersion;
  }
  const owner = input.owner.trim();
  if (owner) {
    body.owner = owner;
  }
  return { ok: true, body };
}

export function fleetUnregisterPath(repoUrl: string): string {
  return `/repave/api/v2/fleet?repo_url=${encodeURIComponent(repoUrl)}`;
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

const COLUMNS: TableColumn<FleetRow>[] = [
  { title: 'Repo', field: 'displayName' },
  { title: 'Family', field: 'family' },
  { title: 'Blueprint', field: 'blueprintName' },
  { title: 'Version', field: 'blueprintVersion' },
  { title: 'Owner', field: 'owner' },
  { title: 'Operator', field: 'operatorPhase' },
  {
    title: 'Remediation',
    field: 'remediationPrUrl',
    render: row =>
      row.remediationPrUrl ? (
        <a href={row.remediationPrUrl} target="_blank" rel="noopener noreferrer">
          {row.remediationPrUrl}
        </a>
      ) : (
        ''
      ),
  },
];

export function FleetPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [rows, setRows] = useState<FleetRow[] | undefined>();
  const [error, setError] = useState('');
  const [repoUrl, setRepoUrl] = useState('');
  const [blueprintName, setBlueprintName] = useState('');
  const [blueprintVersion, setBlueprintVersion] = useState('');
  const [owner, setOwner] = useState('');
  const [submitMessage, setSubmitMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [unregistering, setUnregistering] = useState('');

  const loadFleet = useCallback(async () => {
    const base = await discoveryApi.getBaseUrl('proxy');
    const response = await fetchApi.fetch(`${base}/repave/api/v2/fleet`);
    const text = await response.text();
    const body = parseJsonBody(text);
    if (!response.ok) {
      throw new Error(
        parseApiDetail(body, `GET /api/v2/fleet returned ${response.status}`),
      );
    }
    return parseFleetPayload(body).rows;
  }, [discoveryApi, fetchApi]);

  const refresh = useCallback(() => {
    loadFleet()
      .then(next => {
        setRows(next);
        setError('');
      })
      .catch(err => {
        setRows(undefined);
        setError(err instanceof Error ? err.message : String(err));
      });
  }, [loadFleet]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function onRegister(event: FormEvent) {
    event.preventDefault();
    const request = buildRegisterRequest({
      repoUrl,
      blueprintName,
      blueprintVersion,
      owner,
    });
    if (!request.ok) {
      setSubmitMessage(request.error);
      return;
    }
    setBusy(true);
    setSubmitMessage('');
    try {
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(`${base}/repave/api/v2/fleet`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(request.body),
      });
      const text = await response.text();
      const body = parseJsonBody(text);
      if (!response.ok) {
        throw new Error(
          parseApiDetail(body, `POST /api/v2/fleet returned ${response.status}`),
        );
      }
      setRepoUrl('');
      setBlueprintName('');
      setBlueprintVersion('');
      setOwner('');
      setSubmitMessage(`Registered ${request.body.repo_url}`);
      refresh();
    } catch (err) {
      setSubmitMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onUnregister(row: FleetRow) {
    setUnregistering(row.repoUrl);
    setSubmitMessage('');
    try {
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(`${base}${fleetUnregisterPath(row.repoUrl)}`, {
        method: 'DELETE',
        headers: { Accept: 'application/json' },
      });
      const text = await response.text();
      const body = parseJsonBody(text);
      if (!response.ok) {
        throw new Error(
          parseApiDetail(body, `DELETE /api/v2/fleet returned ${response.status}`),
        );
      }
      setSubmitMessage(`Unregistered ${row.repoUrl}`);
      refresh();
    } catch (err) {
      setSubmitMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setUnregistering('');
    }
  }

  const columns: TableColumn<FleetRow>[] = [
    ...COLUMNS,
    {
      title: '',
      field: 'repoUrl',
      sorting: false,
      searchable: false,
      render: row => (
        <Button
          size="small"
          onClick={() => {
            void onUnregister(row);
          }}
          disabled={unregistering === row.repoUrl}
        >
          Unregister
        </Button>
      ),
    },
  ];

  return (
    <Page themeId="tool">
      <Header
        title="Fleet"
        subtitle="Registered repos from GET /api/v2/fleet. Register and unregister require the admin role."
      />
      <Content>
        {error ? <p>{error}</p> : null}
        {rows === undefined && !error ? <Progress /> : null}
        {rows ? (
          <Table
            options={{ paging: rows.length > 20, search: true, padding: 'dense' }}
            columns={columns}
            data={rows}
            emptyContent={<p>No repos registered yet.</p>}
          />
        ) : null}
        {rows ? (
          <InfoCard title="Register a repo">
            <form onSubmit={onRegister}>
              <TextField
                label="Repository URL"
                value={repoUrl}
                onChange={event => setRepoUrl(event.target.value)}
                helperText="https:// or git@ URL"
                fullWidth
                margin="normal"
                required
              />
              <TextField
                label="Blueprint name"
                value={blueprintName}
                onChange={event => setBlueprintName(event.target.value)}
                helperText="Required — for example terraform-module-generic"
                fullWidth
                margin="normal"
                required
              />
              <TextField
                label="Blueprint version"
                value={blueprintVersion}
                onChange={event => setBlueprintVersion(event.target.value)}
                fullWidth
                margin="normal"
              />
              <TextField
                label="Owner"
                value={owner}
                onChange={event => setOwner(event.target.value)}
                fullWidth
                margin="normal"
              />
              <Button type="submit" color="primary" variant="contained" disabled={busy}>
                Register
              </Button>
            </form>
          </InfoCard>
        ) : null}
        {submitMessage ? <p>{submitMessage}</p> : null}
      </Content>
    </Page>
  );
}
