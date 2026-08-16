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
import { queryParam } from './queryParam';
import {
  canReplayRun,
  parseApiDetail,
  parseRunDetail,
  replayPath,
  type PreviewFile,
  type RunRow,
} from './RunsPage';

const POLL_MS = 5_000;

export function runConsolePath(runId: string): string {
  const value = runId.trim();
  return value ? `/run-console?run=${encodeURIComponent(value)}` : '/run-console';
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

const FILE_COLUMNS: TableColumn<PreviewFile>[] = [
  { title: 'Path', field: 'path' },
  {
    title: 'Preview',
    field: 'content',
    render: row => <pre>{row.content}</pre>,
  },
];

export function RunConsolePage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [runId, setRunId] = useState(() => queryParam(window.location.search, 'run'));
  const [row, setRow] = useState<RunRow | undefined>();
  const [error, setError] = useState('');
  const [replayError, setReplayError] = useState('');
  const [busy, setBusy] = useState(false);

  const loadRun = useCallback(
    async (nextId: string) => {
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(
        `${base}/repave/api/v2/runs/${encodeURIComponent(nextId)}`,
      );
      const text = await response.text();
      const body = parseJsonBody(text);
      if (!response.ok) {
        throw new Error(
          parseApiDetail(body, `GET /api/v2/runs/${nextId} returned ${response.status}`),
        );
      }
      const parsed = parseRunDetail(body);
      if (!parsed) {
        throw new Error(`GET /api/v2/runs/${nextId} did not return a run`);
      }
      return parsed;
    },
    [discoveryApi, fetchApi],
  );

  useEffect(() => {
    let cancelled = false;
    if (!runId) {
      setRow(undefined);
      return () => {
        cancelled = true;
      };
    }
    const refresh = () => {
      loadRun(runId)
        .then(next => {
          if (!cancelled) {
            setRow(next);
            setError('');
          }
        })
        .catch(err => {
          if (!cancelled) {
            setError(err instanceof Error ? err.message : String(err));
          }
        });
    };
    refresh();
    const timer = window.setInterval(refresh, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [loadRun, runId]);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const next = runId.trim();
    setRunId(next);
    window.history.replaceState(null, '', runConsolePath(next));
  }

  async function onReplay() {
    if (!row || !canReplayRun(row.status)) {
      return;
    }
    setBusy(true);
    setReplayError('');
    try {
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(`${base}/repave/api/v2${replayPath(row.runId)}`, {
        method: 'POST',
        headers: { Accept: 'application/json' },
      });
      const text = await response.text();
      const body = parseJsonBody(text);
      if (!response.ok) {
        throw new Error(
          parseApiDetail(body, `POST /api/v2${replayPath(row.runId)} returned ${response.status}`),
        );
      }
      const parsed = parseRunDetail(body);
      if (parsed) {
        setRow(parsed);
      }
    } catch (err) {
      setReplayError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page themeId="tool">
      <Header
        title="Run console"
        subtitle="Poll a durability run, preview dry-run files, and replay failures."
      />
      <Content>
        <form onSubmit={onSubmit}>
          <TextField
            label="Run id"
            value={runId}
            onChange={event => setRunId(event.target.value)}
            helperText="Uses GET /api/v2/runs/{id}"
          />
          <Button color="primary" type="submit">
            Load run
          </Button>
        </form>
        {error ? <p>{error}</p> : null}
        {runId && row === undefined && !error ? <Progress /> : null}
        {row ? (
          <InfoCard title={`Run ${row.runId}`}>
            <p>Status: {row.status}</p>
            <p>Mode: {row.mode}</p>
            {row.kind ? <p>Kind: {row.kind}</p> : null}
            {row.blueprint ? <p>Blueprint: {row.blueprint}</p> : null}
            {row.gatesOutcome ? <p>Gates: {row.gatesOutcome}</p> : null}
            {row.error ? <p>{row.error}</p> : null}
            {replayError ? <p>{replayError}</p> : null}
            {canReplayRun(row.status) ? (
              <Button
                color="primary"
                variant="contained"
                disabled={busy}
                onClick={() => {
                  void onReplay();
                }}
              >
                Replay run
              </Button>
            ) : null}
            {row.previewFiles.length ? (
              <Table
                options={{ paging: row.previewFiles.length > 8, search: true, padding: 'dense' }}
                columns={FILE_COLUMNS}
                data={row.previewFiles}
              />
            ) : null}
          </InfoCard>
        ) : null}
      </Content>
    </Page>
  );
}
