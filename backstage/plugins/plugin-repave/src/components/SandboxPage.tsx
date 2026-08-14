import { useEffect, useState, type FormEvent } from 'react';
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
import FormControlLabel from '@material-ui/core/FormControlLabel';
import Checkbox from '@material-ui/core/Checkbox';

const STACK_NAME_RE = /^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$/;

export type DeploymentSetRow = {
  id: string;
  label: string;
  description: string;
  workloadProfile: string;
  envClass: string;
  ttlHours: number;
  cloudProvider: string;
  environment: string;
};

export type SandboxCatalog = {
  rows: DeploymentSetRow[];
  vendAvailable: boolean;
  developerLab: boolean;
  defaultOwner: string;
};

export function isValidStackName(value: string): boolean {
  return STACK_NAME_RE.test(value.trim());
}

export function rowsFromDeploymentSets(items: unknown[]): DeploymentSetRow[] {
  return items
    .filter(item => item && typeof item === 'object')
    .map(item => {
      const record = item as Record<string, unknown>;
      return {
        id: String(record.id ?? ''),
        label: String(record.label ?? record.id ?? ''),
        description: String(record.description ?? ''),
        workloadProfile: String(record.workload_profile ?? ''),
        envClass: String(record.class ?? 'sandbox'),
        ttlHours: Number(record.ttl_hours ?? 0),
        cloudProvider: String(record.cloud_provider ?? ''),
        environment: String(record.environment ?? ''),
      };
    })
    .filter(row => row.id)
    .sort((left, right) => left.label.localeCompare(right.label));
}

export function parseSandboxCatalog(body: unknown): SandboxCatalog {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const items = Array.isArray(record.deployment_sets) ? record.deployment_sets : [];
  return {
    rows: rowsFromDeploymentSets(items),
    vendAvailable: Boolean(record.vend_available),
    developerLab: Boolean(record.developer_lab),
    defaultOwner: String(record.default_owner ?? 'group:platform'),
  };
}

export function buildVendRequest(input: {
  deploymentSet: string;
  stackName: string;
  owner: string;
  dryRun: boolean;
}): { ok: true; body: Record<string, unknown> } | { ok: false; error: string } {
  const deploymentSet = input.deploymentSet.trim();
  const stackName = input.stackName.trim();
  if (!deploymentSet) {
    return { ok: false, error: 'Pick a deployment set' };
  }
  if (!isValidStackName(stackName)) {
    return {
      ok: false,
      error: 'Stack name must be 3-63 lowercase letters, numbers, and hyphens',
    };
  }
  return {
    ok: true,
    body: {
      deployment_set: deploymentSet,
      stack_name: stackName,
      owner: input.owner.trim(),
      dry_run: input.dryRun,
    },
  };
}

const COLUMNS: TableColumn<DeploymentSetRow>[] = [
  { title: 'Set', field: 'label' },
  { title: 'Profile', field: 'workloadProfile' },
  { title: 'Class', field: 'envClass' },
  { title: 'TTL', field: 'ttlHours', render: row => `${row.ttlHours}h` },
  { title: 'Cloud', field: 'cloudProvider' },
  { title: 'Environment', field: 'environment' },
];

export function SandboxPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [catalog, setCatalog] = useState<SandboxCatalog | undefined>();
  const [error, setError] = useState('');
  const [selected, setSelected] = useState('');
  const [stackName, setStackName] = useState('');
  const [owner, setOwner] = useState('');
  const [dryRun, setDryRun] = useState(true);
  const [submitMessage, setSubmitMessage] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    discoveryApi
      .getBaseUrl('proxy')
      .then(base => fetchApi.fetch(`${base}/repave/api/v2/deployment-sets`))
      .then(async response => {
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
          throw new Error(
            `GET /api/v2/deployment-sets returned ${response.status}: ${detail}`,
          );
        }
        return parseSandboxCatalog(body);
      })
      .then(parsed => {
        if (cancelled) {
          return;
        }
        setCatalog(parsed);
        setOwner(parsed.defaultOwner);
        if (parsed.rows[0]) {
          setSelected(parsed.rows[0].id);
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

  const title = catalog?.developerLab ? 'Developer lab' : 'Sandbox';
  const actionLabel = catalog?.developerLab
    ? 'Request developer lab'
    : 'Request sandbox';

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const request = buildVendRequest({
      deploymentSet: selected,
      stackName,
      owner,
      dryRun,
    });
    if (!request.ok) {
      setSubmitMessage(request.error);
      return;
    }
    setBusy(true);
    setSubmitMessage('');
    try {
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(`${base}/repave/api/v2/environments/vend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(request.body),
      });
      const text = await response.text();
      let body: Record<string, unknown> = {};
      try {
        body = text ? (JSON.parse(text) as Record<string, unknown>) : {};
      } catch {
        body = { detail: text };
      }
      if (!response.ok) {
        throw new Error(String(body.detail ?? text ?? response.status));
      }
      const runId = String(body.run_id ?? '');
      setSubmitMessage(
        runId
          ? `Queued ${dryRun ? 'plan' : 'apply'} run ${runId}`
          : 'Sandbox request queued',
      );
    } catch (err) {
      setSubmitMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page themeId="tool">
      <Header
        title={title}
        subtitle="Pick a deployment set. Repave opens a GitOps pull request; your CD toolchain applies it."
      />
      <Content>
        {error ? <p>{error}</p> : null}
        {catalog === undefined && !error ? <Progress /> : null}
        {catalog ? (
          <>
            {!catalog.vendAvailable ? (
              <p>
                Live requests need environment vending and async runs. You can
                still review profiles and plan a request.
              </p>
            ) : null}
            <Table
              options={{
                paging: catalog.rows.length > 10,
                search: true,
                padding: 'dense',
                selection: false,
              }}
              columns={COLUMNS}
              data={catalog.rows}
              onRowClick={(_event, row) => {
                if (row) {
                  setSelected(row.id);
                }
              }}
              emptyContent={<p>No deployment sets are configured yet.</p>}
            />
            {catalog.rows.length ? (
              <InfoCard title="Request">
                <form onSubmit={onSubmit}>
                  <p>
                    Selected set: <strong>{selected || 'none'}</strong>
                  </p>
                  <TextField
                    label="Stack name"
                    value={stackName}
                    onChange={event => setStackName(event.target.value)}
                    helperText="Lowercase letters, numbers, and hyphens"
                    fullWidth
                    margin="normal"
                    required
                  />
                  <TextField
                    label="Owner"
                    value={owner}
                    onChange={event => setOwner(event.target.value)}
                    fullWidth
                    margin="normal"
                  />
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={dryRun}
                        onChange={event => setDryRun(event.target.checked)}
                        color="primary"
                      />
                    }
                    label="Plan only (no GitOps PR)"
                  />
                  <div>
                    <Button
                      type="submit"
                      color="primary"
                      variant="contained"
                      disabled={busy || !catalog.vendAvailable}
                    >
                      {actionLabel}
                    </Button>
                  </div>
                  {submitMessage ? <p>{submitMessage}</p> : null}
                </form>
              </InfoCard>
            ) : null}
          </>
        ) : null}
      </Content>
    </Page>
  );
}
