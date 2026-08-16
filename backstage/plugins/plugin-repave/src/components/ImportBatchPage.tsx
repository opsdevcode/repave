import { useState, type FormEvent } from 'react';
import {
  Content,
  Header,
  InfoCard,
  Page,
  Table,
  type TableColumn,
} from '@backstage/core-components';
import { discoveryApiRef, fetchApiRef, useApi } from '@backstage/core-plugin-api';
import Button from '@material-ui/core/Button';
import Checkbox from '@material-ui/core/Checkbox';
import FormControlLabel from '@material-ui/core/FormControlLabel';
import TextField from '@material-ui/core/TextField';
import { parseApiDetail, parseImportPlan, type ImportPlanView } from './ImportPage';

export type BatchFailure = {
  target: string;
  error: string;
};

export type BatchPlanView = {
  ok: boolean;
  count: number;
  items: ImportPlanView[];
  failures: BatchFailure[];
};

export type BatchApplyItem = {
  target: string;
  pullRequestUrl: string;
  gitBranch: string;
};

export type BatchApplyView = {
  ok: boolean;
  count: number;
  items: BatchApplyItem[];
  failures: BatchFailure[];
  fleetRegistered: number;
};

export function parseTargetLines(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean);
}

export function buildBatchRequest(input: {
  targets: string;
  org: string;
  topic: string;
  blueprint: string;
  withGates: boolean;
  useFamilyBlueprints: boolean;
}): { ok: true; body: Record<string, unknown> } | { ok: false; error: string } {
  const targets = parseTargetLines(input.targets);
  const org = input.org.trim();
  if (!targets.length && !org) {
    return { ok: false, error: 'Paste repository URLs or set a GitHub org' };
  }
  const body: Record<string, unknown> = {
    targets,
    with_gates: input.withGates,
    use_family_blueprints: input.useFamilyBlueprints,
  };
  if (org) {
    body.org = org;
  }
  const topic = input.topic.trim();
  if (topic) {
    body.topic = topic;
  }
  const blueprint = input.blueprint.trim();
  if (blueprint) {
    body.blueprint = blueprint;
  }
  return { ok: true, body };
}

export function parseBatchFailures(value: unknown): BatchFailure[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter(item => item && typeof item === 'object')
    .map(item => {
      const row = item as Record<string, unknown>;
      return {
        target: String(row.target ?? ''),
        error: String(row.error ?? ''),
      };
    })
    .filter(row => row.target || row.error);
}

export function parseBatchPlan(body: unknown): BatchPlanView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const items = Array.isArray(record.items)
    ? record.items.map(item => parseImportPlan(item)).filter(item => item.target)
    : [];
  return {
    ok: Boolean(record.ok),
    count: Number(record.count ?? items.length),
    items,
    failures: parseBatchFailures(record.failures),
  };
}

export function parseBatchApply(body: unknown): BatchApplyView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const items = Array.isArray(record.items)
    ? record.items
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const row = item as Record<string, unknown>;
          const plan =
            row.plan && typeof row.plan === 'object'
              ? (row.plan as Record<string, unknown>)
              : {};
          return {
            target: String(plan.target ?? row.target ?? ''),
            pullRequestUrl: String(row.pull_request_url ?? ''),
            gitBranch: String(row.git_branch ?? ''),
          };
        })
        .filter(row => row.target || row.pullRequestUrl)
    : [];
  const registered = Array.isArray(record.fleet_registered) ? record.fleet_registered : [];
  return {
    ok: Boolean(record.ok),
    count: Number(record.count ?? items.length),
    items,
    failures: parseBatchFailures(record.failures),
    fleetRegistered: registered.filter(Boolean).length,
  };
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

const PLAN_COLUMNS: TableColumn<ImportPlanView>[] = [
  { title: 'Target', field: 'target' },
  { title: 'Blueprint', field: 'blueprintName' },
  { title: 'OK', field: 'ok', render: row => (row.ok ? 'Yes' : 'No') },
  { title: 'Summary', field: 'summary' },
];

const FAILURE_COLUMNS: TableColumn<BatchFailure>[] = [
  { title: 'Target', field: 'target' },
  { title: 'Error', field: 'error' },
];

const APPLY_COLUMNS: TableColumn<BatchApplyItem>[] = [
  { title: 'Target', field: 'target' },
  { title: 'Branch', field: 'gitBranch' },
  {
    title: 'Pull request',
    field: 'pullRequestUrl',
    render: row =>
      row.pullRequestUrl ? (
        <a href={row.pullRequestUrl} target="_blank" rel="noopener noreferrer">
          {row.pullRequestUrl}
        </a>
      ) : (
        ''
      ),
  },
];

export function ImportBatchPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [targets, setTargets] = useState('');
  const [org, setOrg] = useState('');
  const [topic, setTopic] = useState('');
  const [blueprint, setBlueprint] = useState('');
  const [withGates, setWithGates] = useState(true);
  const [useFamilyBlueprints, setUseFamilyBlueprints] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [plan, setPlan] = useState<BatchPlanView | undefined>();
  const [applyResult, setApplyResult] = useState<BatchApplyView | undefined>();

  async function postBatch(path: '/imports/batch/plan' | '/imports/batch/apply') {
    const request = buildBatchRequest({
      targets,
      org,
      topic,
      blueprint,
      withGates,
      useFamilyBlueprints,
    });
    if (!request.ok) {
      setError(request.error);
      setPlan(undefined);
      setApplyResult(undefined);
      return;
    }
    setBusy(true);
    setError('');
    if (path === '/imports/batch/plan') {
      setPlan(undefined);
      setApplyResult(undefined);
    }
    try {
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(`${base}/repave/api/v2${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(request.body),
      });
      const text = await response.text();
      const body = parseJsonBody(text);
      if (!response.ok) {
        throw new Error(parseApiDetail(body, `POST /api/v2${path} returned ${response.status}`));
      }
      if (path === '/imports/batch/plan') {
        setPlan(parseBatchPlan(body));
      } else {
        setApplyResult(parseBatchApply(body));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onPlan(event: FormEvent) {
    event.preventDefault();
    await postBatch('/imports/batch/plan');
  }

  const canApply = Boolean(plan?.items.length);

  return (
    <Page themeId="tool">
      <Header
        title="Batch import"
        subtitle="Plan many repos from a URL list or GitHub org. Apply uses the engine GitHub token."
      />
      <Content>
        <InfoCard title="Preview batch">
          <form onSubmit={onPlan}>
            <TextField
              label="Repository URLs"
              value={targets}
              onChange={event => setTargets(event.target.value)}
              helperText="One https or git@ URL per line. Optional when org is set."
              fullWidth
              margin="normal"
              multiline
              minRows={4}
            />
            <TextField
              label="GitHub org"
              value={org}
              onChange={event => setOrg(event.target.value)}
              helperText="Optional — discover repos in this org"
              fullWidth
              margin="normal"
            />
            <TextField
              label="Topic"
              value={topic}
              onChange={event => setTopic(event.target.value)}
              helperText="Optional GitHub topic filter"
              fullWidth
              margin="normal"
            />
            <TextField
              label="Blueprint override"
              value={blueprint}
              onChange={event => setBlueprint(event.target.value)}
              helperText="Optional — otherwise detect per repo"
              fullWidth
              margin="normal"
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={withGates}
                  onChange={event => setWithGates(event.target.checked)}
                  color="primary"
                />
              }
              label="Run gates on each plan"
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={useFamilyBlueprints}
                  onChange={event => setUseFamilyBlueprints(event.target.checked)}
                  color="primary"
                />
              }
              label="Pick blueprint from artifact family"
            />
            <div>
              <Button type="submit" color="primary" variant="contained" disabled={busy}>
                Preview batch
              </Button>
            </div>
          </form>
        </InfoCard>
        {error ? <p>{error}</p> : null}
        {plan ? (
          <InfoCard title={plan.ok ? 'Batch preview' : 'Batch preview (issues)'}>
            <p>
              {plan.count} planned
              {plan.failures.length ? `, ${plan.failures.length} failed` : ''}
            </p>
            <Table
              options={{ paging: plan.items.length > 10, search: true, padding: 'dense' }}
              columns={PLAN_COLUMNS}
              data={plan.items}
              emptyContent={<p>No plans in this batch.</p>}
            />
            {plan.failures.length ? (
              <Table
                title="Failures"
                options={{ paging: plan.failures.length > 10, search: true, padding: 'dense' }}
                columns={FAILURE_COLUMNS}
                data={plan.failures}
              />
            ) : null}
            {canApply ? (
              <Button
                color="primary"
                variant="contained"
                disabled={busy}
                onClick={() => {
                  void postBatch('/imports/batch/apply');
                }}
              >
                Open import pull requests
              </Button>
            ) : (
              <p>Resolve failures or add targets before opening pull requests.</p>
            )}
          </InfoCard>
        ) : null}
        {applyResult ? (
          <InfoCard title={applyResult.ok ? 'Batch apply' : 'Batch apply (partial)'}>
            <p>
              {applyResult.count} pull requests
              {applyResult.fleetRegistered
                ? `, ${applyResult.fleetRegistered} registered in fleet`
                : ''}
            </p>
            <Table
              options={{ paging: applyResult.items.length > 10, search: true, padding: 'dense' }}
              columns={APPLY_COLUMNS}
              data={applyResult.items}
              emptyContent={<p>No pull requests opened.</p>}
            />
            {applyResult.failures.length ? (
              <Table
                title="Apply failures"
                options={{ paging: applyResult.failures.length > 10, search: false, padding: 'dense' }}
                columns={FAILURE_COLUMNS}
                data={applyResult.failures}
              />
            ) : null}
          </InfoCard>
        ) : null}
      </Content>
    </Page>
  );
}
