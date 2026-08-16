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

export type OrgScanRepo = {
  url: string;
  name: string;
  governed: boolean;
  family: string;
  artifact: string;
  percent: string;
  blueprint: string;
  error: string;
};

export type OrgScanView = {
  org: string;
  listed: number;
  truncated: boolean;
  discoveryMode: string;
  searchQuery: string;
  repos: OrgScanRepo[];
};

const SCAN_FAMILIES = ['terraform', 'ansible', 'helm'] as const;

export function buildBatchRequest(input: {
  targets: string;
  org: string;
  topic: string;
  blueprint: string;
  withGates: boolean;
  useFamilyBlueprints: boolean;
  targetBlueprints?: Record<string, string>;
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
  if (input.targetBlueprints && Object.keys(input.targetBlueprints).length) {
    body.target_blueprints = input.targetBlueprints;
  }
  return { ok: true, body };
}

export function buildOrgScanRequest(input: {
  org: string;
  topic: string;
  language: string;
  pushedSince: string;
  families: readonly string[];
  skipGoverned: boolean;
  excludeArchived: boolean;
  excludeForks: boolean;
}): { ok: true; body: Record<string, unknown> } | { ok: false; error: string } {
  const org = input.org.trim();
  if (!org) {
    return { ok: false, error: 'GitHub org is required to scan' };
  }
  const body: Record<string, unknown> = {
    org,
    skip_governed: input.skipGoverned,
    exclude_archived: input.excludeArchived,
    exclude_forks: input.excludeForks,
  };
  const families = input.families.map(item => item.trim()).filter(Boolean);
  if (families.length) {
    body.families = families;
  }
  const topic = input.topic.trim();
  if (topic) {
    body.topic = topic;
  }
  const language = input.language.trim();
  if (language) {
    body.language = language;
  }
  const pushedSince = input.pushedSince.trim();
  if (pushedSince) {
    body.pushed_since = pushedSince;
  }
  return { ok: true, body };
}

export function parseOrgScanResult(body: unknown): OrgScanView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const repos = Array.isArray(record.repos)
    ? record.repos
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const row = item as Record<string, unknown>;
          const candidate =
            row.top_candidate && typeof row.top_candidate === 'object'
              ? (row.top_candidate as Record<string, unknown>)
              : {};
          const percent = candidate.percent;
          return {
            url: String(row.url ?? ''),
            name: String(row.name ?? ''),
            governed: Boolean(row.governed),
            family: String(candidate.family ?? ''),
            artifact: String(candidate.artifact_type ?? ''),
            percent:
              percent === null || percent === undefined || percent === ''
                ? ''
                : `${percent}%`,
            blueprint: String(candidate.blueprint_name ?? ''),
            error: String(row.classification_error ?? ''),
          };
        })
        .filter(row => row.url)
    : [];
  return {
    org: String(record.org ?? ''),
    listed: Number(record.listed ?? repos.length),
    truncated: Boolean(record.truncated),
    discoveryMode: String(record.discovery_mode ?? ''),
    searchQuery: String(record.search_query ?? ''),
    repos,
  };
}

export function urlsFromScan(repos: OrgScanRepo[]): string[] {
  return repos.map(row => row.url).filter(Boolean);
}

export function targetBlueprintsFromScan(repos: OrgScanRepo[]): Record<string, string> {
  const mapping: Record<string, string> = {};
  for (const row of repos) {
    if (row.url && row.blueprint) {
      mapping[row.url] = row.blueprint;
    }
  }
  return mapping;
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

const SCAN_COLUMNS: TableColumn<OrgScanRepo>[] = [
  { title: 'Repository', field: 'name' },
  { title: 'Family', field: 'family' },
  { title: 'Artifact', field: 'artifact' },
  { title: 'Match', field: 'percent' },
  { title: 'Blueprint', field: 'blueprint' },
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
  const [language, setLanguage] = useState('');
  const [pushedSince, setPushedSince] = useState('');
  const [families, setFamilies] = useState<string[]>(['terraform', 'ansible']);
  const [skipGoverned, setSkipGoverned] = useState(true);
  const [targetBlueprints, setTargetBlueprints] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [plan, setPlan] = useState<BatchPlanView | undefined>();
  const [applyResult, setApplyResult] = useState<BatchApplyView | undefined>();
  const [scan, setScan] = useState<OrgScanView | undefined>();

  function toggleFamily(family: string, checked: boolean) {
    setFamilies(current =>
      checked ? Array.from(new Set([...current, family])) : current.filter(item => item !== family),
    );
  }

  async function postBatch(path: '/imports/batch/plan' | '/imports/batch/apply') {
    const request = buildBatchRequest({
      targets,
      org,
      topic,
      blueprint,
      withGates,
      useFamilyBlueprints,
      targetBlueprints,
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

  async function onScan(event: FormEvent) {
    event.preventDefault();
    const request = buildOrgScanRequest({
      org,
      topic,
      language,
      pushedSince,
      families,
      skipGoverned,
      excludeArchived: true,
      excludeForks: true,
    });
    if (!request.ok) {
      setError(request.error);
      setScan(undefined);
      return;
    }
    setBusy(true);
    setError('');
    setScan(undefined);
    try {
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(`${base}/repave/api/v2/github/org-scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(request.body),
      });
      const text = await response.text();
      const body = parseJsonBody(text);
      if (!response.ok) {
        throw new Error(
          parseApiDetail(body, `POST /api/v2/github/org-scan returned ${response.status}`),
        );
      }
      setScan(parseOrgScanResult(body));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function addScanToBatch() {
    if (!scan?.repos.length) {
      return;
    }
    setTargets(urlsFromScan(scan.repos).join('\n'));
    const mapping = targetBlueprintsFromScan(scan.repos);
    setTargetBlueprints(mapping);
    if (Object.keys(mapping).length) {
      setUseFamilyBlueprints(true);
    }
    setPlan(undefined);
    setApplyResult(undefined);
  }

  const canApply = Boolean(plan?.items.length);

  return (
    <Page themeId="tool">
      <Header
        title="Batch import"
        subtitle="Scan an org or paste URLs, then plan. Apply uses the engine GitHub token."
      />
      <Content>
        <InfoCard title="Scan organization">
          <form onSubmit={onScan}>
            <TextField
              label="GitHub org"
              value={org}
              onChange={event => setOrg(event.target.value)}
              helperText="Required for scan. Uses the engine GitHub token."
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
              label="Language"
              value={language}
              onChange={event => setLanguage(event.target.value)}
              helperText="Optional GitHub language filter (for example HCL)"
              fullWidth
              margin="normal"
            />
            <TextField
              label="Pushed since"
              value={pushedSince}
              onChange={event => setPushedSince(event.target.value)}
              helperText="Optional YYYY-MM-DD"
              fullWidth
              margin="normal"
            />
            <p>Artifact families (post-scan filter)</p>
            {SCAN_FAMILIES.map(family => (
              <FormControlLabel
                key={family}
                control={
                  <Checkbox
                    checked={families.includes(family)}
                    onChange={event => toggleFamily(family, event.target.checked)}
                    color="primary"
                  />
                }
                label={family}
              />
            ))}
            <div>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={skipGoverned}
                    onChange={event => setSkipGoverned(event.target.checked)}
                    color="primary"
                  />
                }
                label="Skip already-governed repos"
              />
            </div>
            <Button type="submit" color="primary" variant="contained" disabled={busy}>
              Scan organization
            </Button>
          </form>
        </InfoCard>
        {scan ? (
          <InfoCard title={scan.truncated ? 'Scan results (limit reached)' : 'Scan results'}>
            <p>
              {scan.repos.length} matched of {scan.listed} listed
              {scan.discoveryMode ? ` · ${scan.discoveryMode}` : ''}
              {scan.searchQuery ? ` · ${scan.searchQuery}` : ''}
            </p>
            <Table
              options={{ paging: scan.repos.length > 10, search: true, padding: 'dense' }}
              columns={SCAN_COLUMNS}
              data={scan.repos}
              emptyContent={<p>No repositories matched the scan filters.</p>}
            />
            {scan.repos.length ? (
              <Button color="primary" variant="contained" onClick={addScanToBatch}>
                Add all to batch import
              </Button>
            ) : null}
          </InfoCard>
        ) : null}
        <InfoCard title="Preview batch">
          <form onSubmit={onPlan}>
            <TextField
              label="Repository URLs"
              value={targets}
              onChange={event => setTargets(event.target.value)}
              helperText="One https or git@ URL per line. Use Add all after a scan, or paste URLs. Optional when org is set."
              fullWidth
              margin="normal"
              multiline
              minRows={4}
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
