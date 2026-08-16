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

export type AddPlanView = {
  target: string;
  blueprintName: string;
  blueprintVersion: string;
  componentId: string;
  summary: string;
  ok: boolean;
  filesAdded: string[];
  filesOverwritten: string[];
  conflicts: string[];
};

export type AddApplyView = {
  gitBranch: string;
  commitSha: string;
};

export function addQueryDefaults(search: string): {
  target: string;
  blueprint: string;
  componentId: string;
} {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  return {
    target: (params.get('repo') ?? params.get('target_repo') ?? '').trim(),
    blueprint: (params.get('blueprint') ?? '').trim(),
    componentId: (params.get('component_id') ?? '').trim(),
  };
}

export function parseApiDetail(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const raw = (body as { detail: unknown }).detail;
    if (typeof raw === 'string' && raw.trim()) {
      return raw.trim();
    }
    if (raw && typeof raw === 'object' && 'conflicts' in raw) {
      const conflicts = (raw as { conflicts: unknown }).conflicts;
      if (Array.isArray(conflicts) && conflicts.length) {
        return `Conflicts: ${conflicts.map(item => String(item)).join(', ')}`;
      }
    }
  }
  return fallback;
}

export function buildAddRequest(input: {
  target: string;
  blueprint: string;
  componentId: string;
  force: boolean;
}): { ok: true; body: Record<string, unknown> } | { ok: false; error: string } {
  const target = input.target.trim();
  const blueprint = input.blueprint.trim();
  if (!target) {
    return { ok: false, error: 'Local checkout path is required' };
  }
  if (!blueprint) {
    return { ok: false, error: 'Blueprint is required' };
  }
  const body: Record<string, unknown> = {
    target_repo: target,
    blueprint,
    force: input.force,
  };
  const componentId = input.componentId.trim();
  if (componentId) {
    body.component_id = componentId;
  }
  return { ok: true, body };
}

function asStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.map(item => String(item)) : [];
}

export function parseAddPlan(body: unknown): AddPlanView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  return {
    target: String(record.target ?? ''),
    blueprintName: String(record.blueprint_name ?? ''),
    blueprintVersion: String(record.blueprint_version ?? ''),
    componentId: String(record.component_id ?? ''),
    summary: String(record.summary ?? ''),
    ok: Boolean(record.ok),
    filesAdded: asStrings(record.files_added),
    filesOverwritten: asStrings(record.files_overwritten),
    conflicts: asStrings(record.conflicts),
  };
}

export function parseAddApply(body: unknown): AddApplyView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  return {
    gitBranch: String(record.git_branch ?? ''),
    commitSha: String(record.commit_sha ?? ''),
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

export function AddComponentPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const defaults = addQueryDefaults(window.location.search);
  const [target, setTarget] = useState(defaults.target);
  const [blueprint, setBlueprint] = useState(defaults.blueprint);
  const [componentId, setComponentId] = useState(defaults.componentId);
  const [force, setForce] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [plan, setPlan] = useState<AddPlanView | undefined>();
  const [applyResult, setApplyResult] = useState<AddApplyView | undefined>();

  useEffect(() => {
    const next = addQueryDefaults(window.location.search);
    if (next.target) {
      setTarget(next.target);
    }
    if (next.blueprint) {
      setBlueprint(next.blueprint);
    }
    if (next.componentId) {
      setComponentId(next.componentId);
    }
  }, []);

  async function postAdd(path: '/components/plan' | '/components/apply') {
    const request = buildAddRequest({ target, blueprint, componentId, force });
    if (!request.ok) {
      setError(request.error);
      setPlan(undefined);
      setApplyResult(undefined);
      return;
    }
    setBusy(true);
    setError('');
    if (path === '/components/plan') {
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
      if (path === '/components/plan') {
        setPlan(parseAddPlan(body));
      } else {
        setApplyResult(parseAddApply(body));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onPlan(event: FormEvent) {
    event.preventDefault();
    await postAdd('/components/plan');
  }

  return (
    <Page themeId="tool">
      <Header
        title="Add component"
        subtitle="Layer a second golden path onto a governed checkout. Apply commits locally; push the branch yourself."
      />
      <Content>
        <InfoCard title="Preview add">
          <form onSubmit={onPlan}>
            <TextField
              label="Local checkout path"
              value={target}
              onChange={event => setTarget(event.target.value)}
              helperText="Server-side path with repave.yaml. Ungoverned repos belong on Import."
              fullWidth
              margin="normal"
              required
            />
            <TextField
              label="Blueprint"
              value={blueprint}
              onChange={event => setBlueprint(event.target.value)}
              helperText="Required — for example helm-chart-generic"
              fullWidth
              margin="normal"
              required
            />
            <TextField
              label="Component id"
              value={componentId}
              onChange={event => setComponentId(event.target.value)}
              helperText="Optional — recorded in spec.components[]"
              fullWidth
              margin="normal"
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={force}
                  onChange={event => setForce(event.target.checked)}
                  color="primary"
                />
              }
              label="Force overwrite when files differ"
            />
            <div>
              <Button type="submit" color="primary" variant="contained" disabled={busy}>
                Preview add
              </Button>
            </div>
          </form>
        </InfoCard>
        {error ? <p>{error}</p> : null}
        {plan ? (
          <InfoCard title="Add preview">
            <StructuredMetadataTable
              metadata={{
                Blueprint: plan.blueprintVersion
                  ? `${plan.blueprintName}@${plan.blueprintVersion}`
                  : plan.blueprintName,
                'Component id': plan.componentId,
                Summary: plan.summary,
              }}
            />
            {fileList('Files added', plan.filesAdded)}
            {fileList('Files overwritten', plan.filesOverwritten)}
            {fileList('Conflicts', plan.conflicts)}
            {plan.ok ? (
              <Button
                color="primary"
                variant="contained"
                disabled={busy}
                onClick={() => {
                  void postAdd('/components/apply');
                }}
              >
                Apply locally
              </Button>
            ) : (
              <p>Resolve conflicts or enable force overwrite before applying.</p>
            )}
          </InfoCard>
        ) : null}
        {applyResult ? (
          <InfoCard title="Add commit">
            <p>
              Branch: <code>{applyResult.gitBranch || 'n/a'}</code>
            </p>
            <p>
              Commit: <code>{applyResult.commitSha || 'n/a'}</code>
            </p>
            <p>Push the branch and open a pull request yourself. Remote clone is not in this API.</p>
          </InfoCard>
        ) : null}
      </Content>
    </Page>
  );
}
