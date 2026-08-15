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
import TextField from '@material-ui/core/TextField';

export type UpgradePlanView = {
  blueprintName: string;
  blueprintVersion: string;
  summary: string;
  changedFileCount: number;
  added: string[];
  modified: string[];
  removed: string[];
  autoMergeAllowed: boolean | undefined;
  autoMergeReason: string;
};

export function looksLikeRepoUrl(value: string): boolean {
  return /^https?:\/\//i.test(value.trim());
}

export function buildPlanRequest(input: {
  target: string;
  blueprint: string;
}): { ok: true; body: Record<string, string> } | { ok: false; error: string } {
  const target = input.target.trim();
  if (!target) {
    return { ok: false, error: 'Repository path or URL is required' };
  }
  const body: Record<string, string> = looksLikeRepoUrl(target)
    ? { repo_url: target }
    : { target_repo: target };
  const blueprint = input.blueprint.trim();
  if (blueprint) {
    body.blueprint = blueprint;
  }
  return { ok: true, body };
}

export function parseUpgradePlan(body: unknown): UpgradePlanView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const auto =
    record.auto_merge && typeof record.auto_merge === 'object'
      ? (record.auto_merge as Record<string, unknown>)
      : undefined;
  const asStrings = (value: unknown): string[] =>
    Array.isArray(value) ? value.map(item => String(item)) : [];
  return {
    blueprintName: String(record.blueprint_name ?? ''),
    blueprintVersion: String(record.blueprint_version ?? ''),
    summary: String(record.summary ?? ''),
    changedFileCount: Number(record.changed_file_count ?? 0),
    added: asStrings(record.added),
    modified: asStrings(record.modified),
    removed: asStrings(record.removed),
    autoMergeAllowed: auto ? Boolean(auto.allowed) : undefined,
    autoMergeReason: auto ? String(auto.reason ?? '') : '',
  };
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

export function UpgradePage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [target, setTarget] = useState('');
  const [blueprint, setBlueprint] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [plan, setPlan] = useState<UpgradePlanView | undefined>();

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const request = buildPlanRequest({ target, blueprint });
    if (!request.ok) {
      setError(request.error);
      setPlan(undefined);
      return;
    }
    setBusy(true);
    setError('');
    setPlan(undefined);
    try {
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(`${base}/repave/api/v2/upgrades/plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(request.body),
      });
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
        throw new Error(detail || `POST /api/v2/upgrades/plan returned ${response.status}`);
      }
      setPlan(parseUpgradePlan(body));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  let autoMergeLabel = '';
  if (plan?.autoMergeAllowed === true) {
    autoMergeLabel = 'Allowed (mechanical pin bump)';
  } else if (plan?.autoMergeAllowed === false) {
    autoMergeLabel = 'Manual review';
  }

  return (
    <Page themeId="tool">
      <Header
        title="Upgrade"
        subtitle="Re-render from repave.yaml and review the file plan. Apply stays on the CLI or operator."
      />
      <Content>
        <InfoCard title="Preview upgrade">
          <form onSubmit={onSubmit}>
            <TextField
              label="Repository path or URL"
              value={target}
              onChange={event => setTarget(event.target.value)}
              helperText="Local checkout with repave.yaml, or an https GitHub URL"
              fullWidth
              margin="normal"
              required
            />
            <TextField
              label="Blueprint override"
              value={blueprint}
              onChange={event => setBlueprint(event.target.value)}
              helperText="Optional — default from repave.yaml"
              fullWidth
              margin="normal"
            />
            <Button type="submit" color="primary" variant="contained" disabled={busy}>
              Preview upgrade
            </Button>
          </form>
        </InfoCard>
        {error ? <p>{error}</p> : null}
        {plan ? (
          <InfoCard title="Upgrade preview">
            <StructuredMetadataTable
              metadata={{
                Blueprint: plan.blueprintVersion
                  ? `${plan.blueprintName}@${plan.blueprintVersion}`
                  : plan.blueprintName,
                Summary: plan.summary,
                'Changed files': String(plan.changedFileCount),
                ...(autoMergeLabel
                  ? {
                      'Auto-merge': autoMergeLabel,
                      ...(plan.autoMergeReason
                        ? { 'Auto-merge reason': plan.autoMergeReason }
                        : {}),
                    }
                  : {}),
              }}
            />
            {fileList('Added', plan.added)}
            {fileList('Modified', plan.modified)}
            {fileList('Removed', plan.removed)}
          </InfoCard>
        ) : null}
      </Content>
    </Page>
  );
}
