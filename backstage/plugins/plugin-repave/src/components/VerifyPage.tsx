import { useState, type FormEvent } from 'react';
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

export type VerifyGate = {
  name: string;
  passed: boolean;
  skipped: boolean;
  message: string;
};

export type VerifyPinChange = {
  field: string;
  before: string;
  after: string;
};

export type VerifyComponentView = {
  componentId: string;
  blueprintName: string;
  ok: boolean;
  gatesPassed: boolean;
  pinsAligned: boolean;
};

export type VerifyResultView = {
  target: string;
  blueprintName: string;
  blueprintVersion: string;
  ok: boolean;
  gatesPassed: boolean;
  pinsAligned: boolean;
  provenancePresent: boolean;
  remote: boolean;
  gates: VerifyGate[];
  pinChanges: VerifyPinChange[];
  components: VerifyComponentView[];
};

export function looksLikeRemoteTarget(value: string): boolean {
  const trimmed = value.trim();
  return /^https?:\/\//i.test(trimmed) || /^git@/.test(trimmed);
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

export function isVerifyResultStatus(status: number): boolean {
  return status === 200 || status === 422;
}

export function buildVerifyRequest(input: {
  target: string;
  blueprint: string;
  ref: string;
  requireRun: boolean;
}): { ok: true; body: Record<string, unknown> } | { ok: false; error: string } {
  const target = input.target.trim();
  if (!target) {
    return { ok: false, error: 'Repository path or URL is required' };
  }
  const body: Record<string, unknown> = looksLikeRemoteTarget(target)
    ? { repo_url: target, require_run: input.requireRun }
    : { path: target, require_run: input.requireRun };
  const blueprint = input.blueprint.trim();
  if (blueprint) {
    body.blueprint = blueprint;
  }
  const ref = input.ref.trim();
  if (ref) {
    body.ref = ref;
  }
  return { ok: true, body };
}

export function gateStatusLabel(gate: VerifyGate): string {
  if (gate.skipped) {
    return 'skipped';
  }
  return gate.passed ? 'passed' : 'failed';
}

function parseGates(value: unknown): VerifyGate[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
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
    .filter(gate => gate.name);
}

function parsePinChanges(value: unknown): VerifyPinChange[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter(item => item && typeof item === 'object')
    .map(item => {
      const row = item as Record<string, unknown>;
      return {
        field: String(row.field ?? ''),
        before: String(row.before ?? ''),
        after: String(row.after ?? ''),
      };
    })
    .filter(row => row.field);
}

export function parseVerifyResult(body: unknown): VerifyResultView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const components = Array.isArray(record.components)
    ? record.components
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const row = item as Record<string, unknown>;
          return {
            componentId: String(row.component_id ?? ''),
            blueprintName: String(row.catalog_blueprint_name ?? ''),
            ok: Boolean(row.ok),
            gatesPassed: Boolean(row.gates_passed),
            pinsAligned: Boolean(row.pins_aligned),
          };
        })
        .filter(row => row.componentId)
    : [];
  return {
    target: String(record.target ?? ''),
    blueprintName: String(record.catalog_blueprint_name ?? ''),
    blueprintVersion: String(record.catalog_blueprint_version ?? ''),
    ok: Boolean(record.ok),
    gatesPassed: Boolean(record.gates_passed),
    pinsAligned: Boolean(record.pins_aligned),
    provenancePresent: Boolean(record.provenance_present),
    remote: Boolean(record.remote),
    gates: parseGates(record.gates),
    pinChanges: parsePinChanges(record.pin_changes),
    components,
  };
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

export function VerifyPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [target, setTarget] = useState('');
  const [blueprint, setBlueprint] = useState('');
  const [ref, setRef] = useState('');
  const [requireRun, setRequireRun] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<VerifyResultView | undefined>();

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const request = buildVerifyRequest({ target, blueprint, ref, requireRun });
    if (!request.ok) {
      setError(request.error);
      setResult(undefined);
      return;
    }
    setBusy(true);
    setError('');
    setResult(undefined);
    try {
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(`${base}/repave/api/v2/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(request.body),
      });
      const text = await response.text();
      const body = parseJsonBody(text);
      if (!isVerifyResultStatus(response.status)) {
        throw new Error(
          parseApiDetail(body, `POST /api/v2/verify returned ${response.status}`),
        );
      }
      setResult(parseVerifyResult(body));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page themeId="tool">
      <Header
        title="Verify"
        subtitle="Run gates and compare provenance pins. HTTP 422 is a failed verify, not a transport error."
      />
      <Content>
        <InfoCard title="Verify a repo">
          <form onSubmit={onSubmit}>
            <TextField
              label="Repository path or URL"
              value={target}
              onChange={event => setTarget(event.target.value)}
              helperText="Local checkout or https / git@ remote"
              fullWidth
              margin="normal"
              required
            />
            <TextField
              label="Blueprint override"
              value={blueprint}
              onChange={event => setBlueprint(event.target.value)}
              helperText="Optional — default from repave.yaml or detection"
              fullWidth
              margin="normal"
            />
            <TextField
              label="Git ref"
              value={ref}
              onChange={event => setRef(event.target.value)}
              helperText="Optional — branch, tag, or SHA for remotes"
              fullWidth
              margin="normal"
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={requireRun}
                  onChange={event => setRequireRun(event.target.checked)}
                  color="primary"
                />
              }
              label="Require optional gates (fail when a tool is missing)"
            />
            <div>
              <Button type="submit" color="primary" variant="contained" disabled={busy}>
                Verify
              </Button>
            </div>
          </form>
        </InfoCard>
        {error ? <p>{error}</p> : null}
        {result ? (
          <InfoCard title={result.ok ? 'Verify passed' : 'Verify failed'}>
            <StructuredMetadataTable
              metadata={{
                Target: result.target,
                Blueprint: result.blueprintVersion
                  ? `${result.blueprintName}@${result.blueprintVersion}`
                  : result.blueprintName,
                Outcome: result.ok ? 'Passed' : 'Failed',
                Gates: result.gatesPassed ? 'Passed' : 'Failed',
                Pins: result.pinsAligned ? 'Aligned' : 'Drift',
                Provenance: result.provenancePresent ? 'Present' : 'Absent',
                Remote: result.remote ? 'Yes' : 'No',
              }}
            />
            {result.gates.length ? (
              <div>
                <p>
                  <strong>Gates</strong>
                </p>
                <ul>
                  {result.gates.map(gate => (
                    <li key={gate.name}>
                      {gate.name}: {gateStatusLabel(gate)}
                      {gate.message ? ` — ${gate.message}` : ''}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {result.pinChanges.length ? (
              <div>
                <p>
                  <strong>Pin drift</strong>
                </p>
                <ul>
                  {result.pinChanges.map(change => (
                    <li key={change.field}>
                      {change.field}: <code>{change.before || '(empty)'}</code>
                      {' → '}
                      <code>{change.after || '(empty)'}</code>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {result.components.length ? (
              <div>
                <p>
                  <strong>Components</strong>
                </p>
                <ul>
                  {result.components.map(component => (
                    <li key={component.componentId}>
                      {component.componentId} ({component.blueprintName}):{' '}
                      {component.ok ? 'passed' : 'failed'}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </InfoCard>
        ) : null}
      </Content>
    </Page>
  );
}
