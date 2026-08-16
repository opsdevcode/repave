import { useState, type FormEvent } from 'react';
import {
  Content,
  Header,
  InfoCard,
  Page,
  StructuredMetadataTable,
  Table,
  type TableColumn,
} from '@backstage/core-components';
import { discoveryApiRef, fetchApiRef, useApi } from '@backstage/core-plugin-api';
import Button from '@material-ui/core/Button';
import Checkbox from '@material-ui/core/Checkbox';
import FormControlLabel from '@material-ui/core/FormControlLabel';
import TextField from '@material-ui/core/TextField';

export type ReclaimResultRow = {
  stackName: string;
  entityId: string;
  mode: string;
  status: string;
  detail: string;
  pullRequestUrl: string;
};

export type ReclaimView = {
  count: number;
  reclaimed: number;
  decommissionReview: number;
  finalized: number;
  skipped: number;
  results: ReclaimResultRow[];
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

export function buildReclaimRequest(input: {
  dryRun: boolean;
  stackName: string;
}): { ok: true; body: Record<string, unknown> } {
  const body: Record<string, unknown> = { dry_run: input.dryRun };
  const stackName = input.stackName.trim();
  if (stackName) {
    body.stack_name = stackName;
  }
  return { ok: true, body };
}

export function reclaimStatus(row: { skipped: boolean; reclaimed: boolean }): string {
  if (row.skipped) {
    return 'skipped';
  }
  if (row.reclaimed) {
    return 'reclaimed';
  }
  return 'pending';
}

export function parseReclaimSummary(body: unknown): ReclaimView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const results = Array.isArray(record.results)
    ? record.results
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const row = item as Record<string, unknown>;
          const skipped = Boolean(row.skipped);
          const reclaimed = Boolean(row.reclaimed);
          return {
            stackName: String(row.stack_name ?? ''),
            entityId: String(row.entity_id ?? ''),
            mode: String(row.mode ?? ''),
            status: reclaimStatus({ skipped, reclaimed }),
            detail: String(row.skip_reason || row.detail || ''),
            pullRequestUrl: String(row.pull_request_url ?? ''),
          };
        })
        .filter(row => row.stackName)
    : [];
  return {
    count: Number(record.count ?? results.length),
    reclaimed: Number(record.reclaimed ?? 0),
    decommissionReview: Number(record.decommission_review ?? 0),
    finalized: Number(record.finalized ?? 0),
    skipped: Number(record.skipped ?? 0),
    results,
  };
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

const RESULT_COLUMNS: TableColumn<ReclaimResultRow>[] = [
  { title: 'Stack', field: 'stackName' },
  { title: 'Mode', field: 'mode' },
  { title: 'Status', field: 'status' },
  { title: 'Detail', field: 'detail' },
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

export function ReclaimPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [stackName, setStackName] = useState('');
  const [dryRun, setDryRun] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [view, setView] = useState<ReclaimView | undefined>();

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const request = buildReclaimRequest({ dryRun, stackName });
    setBusy(true);
    setError('');
    setView(undefined);
    try {
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(`${base}/repave/api/v2/environments/reclaim`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(request.body),
      });
      const text = await response.text();
      const body = parseJsonBody(text);
      if (!response.ok) {
        throw new Error(
          parseApiDetail(body, `POST /api/v2/environments/reclaim returned ${response.status}`),
        );
      }
      setView(parseReclaimSummary(body));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page themeId="tool">
      <Header
        title="Reclaim"
        subtitle="Expire sandbox stacks via POST /api/v2/environments/reclaim. Apply uses the engine GitHub token."
      />
      <Content>
        <InfoCard title="Reclaim expired environments">
          <form onSubmit={onSubmit}>
            <TextField
              label="Stack name"
              value={stackName}
              onChange={event => setStackName(event.target.value)}
              helperText="Optional — leave blank to reclaim every expired stack"
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
              label="Dry run (preview only)"
            />
            <div>
              <Button type="submit" color="primary" variant="contained" disabled={busy}>
                {dryRun ? 'Preview reclaim' : 'Apply reclaim'}
              </Button>
            </div>
          </form>
        </InfoCard>
        {error ? <p>{error}</p> : null}
        {view ? (
          <>
            <InfoCard title={dryRun ? 'Preview' : 'Reclaim result'}>
              <StructuredMetadataTable
                metadata={{
                  Count: String(view.count),
                  Reclaimed: String(view.reclaimed),
                  'Decommission review': String(view.decommissionReview),
                  Finalized: String(view.finalized),
                  Skipped: String(view.skipped),
                }}
              />
            </InfoCard>
            <Table
              title="Stacks"
              options={{ paging: view.results.length > 10, search: true, padding: 'dense' }}
              columns={RESULT_COLUMNS}
              data={view.results}
              emptyContent={<p>No expired environments to reclaim.</p>}
            />
          </>
        ) : null}
      </Content>
    </Page>
  );
}
