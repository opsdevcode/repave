import { useEffect, useState, type FormEvent } from 'react';
import {
  Content,
  Header,
  InfoCard,
  Page,
  StructuredMetadataTable,
} from '@backstage/core-components';
import { discoveryApiRef, fetchApiRef, useApi } from '@backstage/core-plugin-api';
import Button from '@material-ui/core/Button';
import Checkbox from '@material-ui/core/Checkbox';
import FormControlLabel from '@material-ui/core/FormControlLabel';
import TextField from '@material-ui/core/TextField';

export type ImportMove = {
  source: string;
  destination: string;
  reason: string;
};

export type ImportGate = {
  name: string;
  passed: boolean;
  skipped: boolean;
  message: string;
};

export type ImportPlanView = {
  target: string;
  blueprintName: string;
  blueprintVersion: string;
  summary: string;
  ok: boolean;
  detected: boolean;
  previewLimited: boolean;
  passingBefore: number;
  passingAfter: number;
  moves: ImportMove[];
  scaffoldAdded: string[];
  unmapped: string[];
  conflicts: string[];
  gates: ImportGate[];
};

export type ImportApplyView = {
  pullRequestUrl: string;
  gitBranch: string;
  fleetRegistered: boolean;
};

export function importQueryDefaults(search: string): { target: string; blueprint: string } {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  return {
    target: (params.get('repo') ?? params.get('target_repo') ?? '').trim(),
    blueprint: (params.get('blueprint') ?? '').trim(),
  };
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

export function buildImportRequest(input: {
  target: string;
  blueprint: string;
  withGates: boolean;
}): { ok: true; body: Record<string, unknown> } | { ok: false; error: string } {
  const target = input.target.trim();
  if (!target) {
    return { ok: false, error: 'Repository path or URL is required' };
  }
  const body: Record<string, unknown> = {
    target_repo: target,
    with_gates: input.withGates,
  };
  const blueprint = input.blueprint.trim();
  if (blueprint) {
    body.blueprint = blueprint;
  }
  return { ok: true, body };
}

function asStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.map(item => String(item)) : [];
}

export function parseImportPlan(body: unknown): ImportPlanView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const scorecard =
    record.scorecard && typeof record.scorecard === 'object'
      ? (record.scorecard as Record<string, unknown>)
      : {};
  const moves = Array.isArray(record.moves)
    ? record.moves
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const move = item as Record<string, unknown>;
          return {
            source: String(move.source ?? ''),
            destination: String(move.destination ?? ''),
            reason: String(move.reason ?? ''),
          };
        })
        .filter(move => move.source || move.destination)
    : [];
  const gates = Array.isArray(record.gates)
    ? record.gates
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const gate = item as Record<string, unknown>;
          return {
            name: String(gate.name ?? ''),
            passed: Boolean(gate.passed),
            skipped: Boolean(gate.skipped),
            message: String(gate.message ?? ''),
          };
        })
        .filter(gate => gate.name)
    : [];
  return {
    target: String(record.target ?? ''),
    blueprintName: String(record.blueprint_name ?? ''),
    blueprintVersion: String(record.blueprint_version ?? ''),
    summary: String(record.summary ?? ''),
    ok: Boolean(record.ok),
    detected: Boolean(record.detected),
    previewLimited: Boolean(record.preview_limited),
    passingBefore: Number(scorecard.passing_before ?? 0),
    passingAfter: Number(scorecard.passing_after ?? 0),
    moves,
    scaffoldAdded: asStrings(record.scaffold_added),
    unmapped: asStrings(record.unmapped),
    conflicts: asStrings(record.conflicts),
    gates,
  };
}

export function gateStatusLabel(gate: ImportGate): string {
  if (gate.skipped) {
    return 'skipped';
  }
  return gate.passed ? 'passed' : 'failed';
}

export function parseImportApply(body: unknown): ImportApplyView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  return {
    pullRequestUrl: String(record.pull_request_url ?? ''),
    gitBranch: String(record.git_branch ?? ''),
    fleetRegistered: Boolean(record.fleet_registered),
  };
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

function fileList(title: string, paths: string[]) {
  if (!paths.length) {
    return null;
  }
  return (
    <div>
      <p>
        <strong>{title}</strong>
      </p>
      <ul>
        {paths.map(path => (
          <li key={`${title}-${path}`}>
            <code>{path}</code>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ImportPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const defaults = importQueryDefaults(window.location.search);
  const [target, setTarget] = useState(defaults.target);
  const [blueprint, setBlueprint] = useState(defaults.blueprint);
  const [withGates, setWithGates] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [plan, setPlan] = useState<ImportPlanView | undefined>();
  const [applyResult, setApplyResult] = useState<ImportApplyView | undefined>();

  useEffect(() => {
    const next = importQueryDefaults(window.location.search);
    if (next.target) {
      setTarget(next.target);
    }
    if (next.blueprint) {
      setBlueprint(next.blueprint);
    }
  }, []);

  async function postImport(path: '/imports/plan' | '/imports/apply') {
    const request = buildImportRequest({ target, blueprint, withGates });
    if (!request.ok) {
      setError(request.error);
      setPlan(undefined);
      setApplyResult(undefined);
      return;
    }
    setBusy(true);
    setError('');
    if (path === '/imports/plan') {
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
      if (path === '/imports/plan') {
        setPlan(parseImportPlan(body));
      } else {
        setApplyResult(parseImportApply(body));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onPlan(event: FormEvent) {
    event.preventDefault();
    await postImport('/imports/plan');
  }

  return (
    <Page themeId="tool">
      <Header
        title="Import"
        subtitle="Preview a legacy repo against a blueprint, then open an import pull request. Batch import stays on the CLI."
      />
      <Content>
        <InfoCard title="Preview import">
          <form onSubmit={onPlan}>
            <TextField
              label="Repository path or URL"
              value={target}
              onChange={event => setTarget(event.target.value)}
              helperText="Local checkout or https GitHub URL. Already-governed repos belong on Upgrade."
              fullWidth
              margin="normal"
              required
            />
            <TextField
              label="Blueprint override"
              value={blueprint}
              onChange={event => setBlueprint(event.target.value)}
              helperText="Optional — detected from the tree when omitted"
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
              label="Run gates on the plan"
            />
            <div>
              <Button type="submit" color="primary" variant="contained" disabled={busy}>
                Preview import
              </Button>
            </div>
          </form>
        </InfoCard>
        {error ? <p>{error}</p> : null}
        {plan ? (
          <InfoCard title="Import preview">
            <StructuredMetadataTable
              metadata={{
                Blueprint: plan.blueprintVersion
                  ? `${plan.blueprintName}@${plan.blueprintVersion}`
                  : plan.blueprintName,
                Summary: plan.summary,
                Detected: plan.detected ? 'Yes' : 'No',
                Scorecard: `${plan.passingAfter} passing after / ${plan.passingBefore} before`,
                ...(plan.previewLimited
                  ? { Preview: 'Limited — scorecard and gates run on apply' }
                  : {}),
              }}
            />
            {plan.moves.length ? (
              <div>
                <p>
                  <strong>Moves</strong>
                </p>
                <ul>
                  {plan.moves.map(move => (
                    <li key={`${move.source}->${move.destination}`}>
                      <code>{move.source}</code>
                      {' → '}
                      <code>{move.destination}</code>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {fileList('Scaffold added', plan.scaffoldAdded)}
            {fileList('Unmapped', plan.unmapped)}
            {fileList('Conflicts', plan.conflicts)}
            {plan.gates.length ? (
              <div>
                <p>
                  <strong>Gates</strong>
                </p>
                <ul>
                  {plan.gates.map(gate => (
                    <li key={gate.name}>
                      {gate.name}: {gateStatusLabel(gate)}
                      {gate.message ? ` — ${gate.message}` : ''}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {plan.ok ? (
              <Button
                color="primary"
                variant="contained"
                disabled={busy}
                onClick={() => {
                  void postImport('/imports/apply');
                }}
              >
                Open import pull request
              </Button>
            ) : (
              <p>Resolve conflicts before opening a pull request.</p>
            )}
          </InfoCard>
        ) : null}
        {applyResult ? (
          <InfoCard title="Import pull request">
            <p>
              Branch: <code>{applyResult.gitBranch || 'n/a'}</code>
            </p>
            {applyResult.pullRequestUrl ? (
              <p>
                <a href={applyResult.pullRequestUrl} target="_blank" rel="noopener noreferrer">
                  {applyResult.pullRequestUrl}
                </a>
              </p>
            ) : (
              <p>Apply succeeded. No pull request URL was returned.</p>
            )}
            {applyResult.fleetRegistered ? <p>Registered in the fleet registry.</p> : null}
          </InfoCard>
        ) : null}
      </Content>
    </Page>
  );
}
