import { useEffect, useState, type FormEvent } from 'react';
import {
  Content,
  Header,
  InfoCard,
  Link,
  Page,
  Progress,
  Table,
  type TableColumn,
} from '@backstage/core-components';
import { discoveryApiRef, fetchApiRef, useApi } from '@backstage/core-plugin-api';
import Button from '@material-ui/core/Button';
import Checkbox from '@material-ui/core/Checkbox';
import FormControlLabel from '@material-ui/core/FormControlLabel';
import TextField from '@material-ui/core/TextField';

const COMPONENT_NAME_RE = /^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$/;

export type ComponentKindRow = {
  id: string;
  label: string;
  blueprint: string;
  description: string;
};

export type ComponentKindsCatalog = {
  rows: ComponentKindRow[];
  vendAvailable: boolean;
  count: number;
};

export function isValidComponentName(value: string): boolean {
  return COMPONENT_NAME_RE.test(value.trim());
}

export function rowsFromComponentKinds(items: unknown[]): ComponentKindRow[] {
  return items
    .filter(item => item && typeof item === 'object')
    .map(item => {
      const record = item as Record<string, unknown>;
      return {
        id: String(record.id ?? ''),
        label: String(record.label ?? record.id ?? ''),
        blueprint: String(record.blueprint ?? ''),
        description: String(record.description ?? ''),
      };
    })
    .filter(row => row.id)
    .sort((left, right) => left.label.localeCompare(right.label));
}

export function parseComponentKinds(body: unknown): ComponentKindsCatalog {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const items = Array.isArray(record.kinds) ? record.kinds : [];
  const rows = rowsFromComponentKinds(items);
  return {
    rows,
    vendAvailable: Boolean(record.vend_available),
    count: Number(record.count ?? rows.length),
  };
}

export function buildComponentVendRequest(input: {
  kind: string;
  name: string;
  owner: string;
  dryRun: boolean;
}): { ok: true; body: Record<string, unknown> } | { ok: false; error: string } {
  const kind = input.kind.trim();
  const name = input.name.trim();
  if (!kind) {
    return { ok: false, error: 'Pick a component kind' };
  }
  if (!isValidComponentName(name)) {
    return {
      ok: false,
      error: 'Name must be 3-63 lowercase letters, numbers, and hyphens',
    };
  }
  const body: Record<string, unknown> = {
    kind,
    name,
    dry_run: input.dryRun,
  };
  const owner = input.owner.trim();
  if (owner) {
    body.owner = owner;
  }
  return { ok: true, body };
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

function parseApiDetail(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = String((body as { detail: unknown }).detail).trim();
    if (detail) {
      return detail;
    }
  }
  return fallback;
}

const COLUMNS: TableColumn<ComponentKindRow>[] = [
  { title: 'Kind', field: 'label' },
  { title: 'Id', field: 'id' },
  { title: 'Blueprint', field: 'blueprint' },
  { title: 'Description', field: 'description' },
];

export function VendComponentPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [catalog, setCatalog] = useState<ComponentKindsCatalog | undefined>();
  const [error, setError] = useState('');
  const [selected, setSelected] = useState('');
  const [name, setName] = useState('');
  const [owner, setOwner] = useState('');
  const [dryRun, setDryRun] = useState(true);
  const [submitMessage, setSubmitMessage] = useState('');
  const [runId, setRunId] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    discoveryApi
      .getBaseUrl('proxy')
      .then(base => fetchApi.fetch(`${base}/repave/api/v2/component-kinds`))
      .then(async response => {
        const text = await response.text();
        const body = parseJsonBody(text);
        if (!response.ok) {
          throw new Error(
            parseApiDetail(body, `GET /api/v2/component-kinds returned ${response.status}`),
          );
        }
        return parseComponentKinds(body);
      })
      .then(parsed => {
        if (cancelled) {
          return;
        }
        setCatalog(parsed);
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

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const request = buildComponentVendRequest({
      kind: selected,
      name,
      owner,
      dryRun,
    });
    if (!request.ok) {
      setSubmitMessage(request.error);
      setRunId('');
      return;
    }
    setBusy(true);
    setSubmitMessage('');
    setRunId('');
    try {
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(`${base}/repave/api/v2/components/vend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(request.body),
      });
      const text = await response.text();
      const body = parseJsonBody(text);
      if (!response.ok) {
        throw new Error(
          parseApiDetail(body, `POST /api/v2/components/vend returned ${response.status}`),
        );
      }
      const queuedId =
        body && typeof body === 'object' && 'run_id' in body
          ? String((body as { run_id: unknown }).run_id ?? '')
          : '';
      setRunId(queuedId);
      setSubmitMessage(
        queuedId
          ? `Queued ${dryRun ? 'plan' : 'apply'} run ${queuedId}`
          : 'Component request queued',
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
        title="Vend component"
        subtitle="Request a managed database, bucket, or queue. Repave opens a GitOps pull request; your CD toolchain applies it."
      />
      <Content>
        {error ? <p>{error}</p> : null}
        {catalog === undefined && !error ? <Progress /> : null}
        {catalog ? (
          <>
            {!catalog.vendAvailable ? (
              <p>
                Live requests need component vending and async runs. You can
                still review kinds and plan a request.
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
              emptyContent={<p>No component kinds are configured yet.</p>}
            />
            {catalog.rows.length ? (
              <InfoCard title="Request">
                <form onSubmit={onSubmit}>
                  <p>
                    Selected kind: <strong>{selected || 'none'}</strong>
                  </p>
                  <TextField
                    label="Name"
                    value={name}
                    onChange={event => setName(event.target.value)}
                    helperText="Lowercase letters, numbers, and hyphens"
                    fullWidth
                    margin="normal"
                    required
                  />
                  <TextField
                    label="Owner"
                    value={owner}
                    onChange={event => setOwner(event.target.value)}
                    helperText="Optional — team or group that owns the component"
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
                      Request component
                    </Button>
                  </div>
                  {submitMessage ? <p>{submitMessage}</p> : null}
                  {runId ? (
                    <p>
                      <Link to="/runs">View run on /runs</Link>
                    </p>
                  ) : null}
                </form>
              </InfoCard>
            ) : null}
          </>
        ) : null}
      </Content>
    </Page>
  );
}
