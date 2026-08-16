import { useCallback, useEffect, useState } from 'react';
import {
  Content,
  Header,
  InfoCard,
  Page,
  Progress,
  StructuredMetadataTable,
  Table,
  type TableColumn,
} from '@backstage/core-components';
import { discoveryApiRef, fetchApiRef, useApi } from '@backstage/core-plugin-api';
import Button from '@material-ui/core/Button';
import { canReplayRun, replayPath } from './RunsPage';

export type DoctorRow = {
  tool: string;
  present: string;
  detected: string;
  pinned: string;
};

export type DeadLetterRow = {
  runId: string;
  status: string;
  kind: string;
  updatedAt: string;
};

export type OpsView = {
  ready: string;
  queuedRuns: number;
  runningRuns: number;
  queueDepth: string;
  asyncEnabled: boolean;
  environmentCount: number;
  vendingEnabled: boolean;
  reclaimCount: string;
  doctor: DoctorRow[];
  deadLetters: DeadLetterRow[];
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

export function parseOpsPayload(body: unknown): OpsView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const readiness =
    record.readiness && typeof record.readiness === 'object'
      ? (record.readiness as Record<string, unknown>)
      : {};
  const preview =
    record.reclaim_preview && typeof record.reclaim_preview === 'object'
      ? (record.reclaim_preview as Record<string, unknown>)
      : {};
  const doctor = Array.isArray(record.doctor_results)
    ? record.doctor_results
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const row = item as Record<string, unknown>;
          return {
            tool: String(row.tool ?? ''),
            present: row.present ? 'yes' : 'no',
            detected: String(row.detected_version ?? ''),
            pinned: String(row.pinned_version ?? ''),
          };
        })
        .filter(row => row.tool)
    : [];
  const deadLetters = Array.isArray(record.dead_letter_runs)
    ? record.dead_letter_runs
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const row = item as Record<string, unknown>;
          return {
            runId: String(row.run_id ?? ''),
            status: String(row.status ?? ''),
            kind: String(row.kind ?? ''),
            updatedAt: String(row.updated_at ?? ''),
          };
        })
        .filter(row => row.runId)
    : [];
  return {
    ready: String(readiness.status ?? 'unknown'),
    queuedRuns: Number(record.queued_runs ?? 0),
    runningRuns: Number(record.running_runs ?? 0),
    queueDepth: record.queue_depth === null || record.queue_depth === undefined
      ? 'n/a'
      : String(record.queue_depth),
    asyncEnabled: Boolean(record.async_generation_enabled),
    environmentCount: Number(record.environment_count ?? 0),
    vendingEnabled: Boolean(record.environment_vending_enabled),
    reclaimCount:
      preview.count === undefined || preview.count === null ? 'n/a' : String(preview.count),
    doctor,
    deadLetters,
  };
}

export function buildEnvReclaimRunBody(): Record<string, unknown> {
  return { kind: 'environment_reclaim', dry_run: false };
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

const DOCTOR_COLUMNS: TableColumn<DoctorRow>[] = [
  { title: 'Tool', field: 'tool' },
  { title: 'Present', field: 'present' },
  { title: 'Detected', field: 'detected' },
  { title: 'Pinned', field: 'pinned' },
];

const DEAD_LETTER_COLUMNS: TableColumn<DeadLetterRow>[] = [
  { title: 'Run', field: 'runId' },
  { title: 'Status', field: 'status' },
  { title: 'Kind', field: 'kind' },
  { title: 'Updated', field: 'updatedAt' },
];

export function OpsPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [view, setView] = useState<OpsView | undefined>();
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const base = await discoveryApi.getBaseUrl('proxy');
    const response = await fetchApi.fetch(`${base}/repave/api/v2/platform/ops`);
    const text = await response.text();
    const body = parseJsonBody(text);
    if (!response.ok) {
      throw new Error(parseApiDetail(body, `GET /api/v2/platform/ops returned ${response.status}`));
    }
    return parseOpsPayload(body);
  }, [discoveryApi, fetchApi]);

  useEffect(() => {
    let cancelled = false;
    load()
      .then(next => {
        if (!cancelled) {
          setView(next);
          setError('');
        }
      })
      .catch(err => {
        if (!cancelled) {
          setView(undefined);
          setError(err instanceof Error ? err.message : String(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [load]);

  const reclaimExpired = async (dryRun: boolean) => {
    setBusy(true);
    setNotice('');
    try {
      const base = await discoveryApi.getBaseUrl('proxy');
      const path = dryRun ? '/environments/reclaim' : '/runs';
      const payload = dryRun ? { dry_run: true } : buildEnvReclaimRunBody();
      const response = await fetchApi.fetch(`${base}/repave/api/v2${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const body = parseJsonBody(await response.text());
      if (!response.ok) {
        throw new Error(
          parseApiDetail(body, `POST /api/v2${path} returned ${response.status}`),
        );
      }
      setNotice(
        dryRun
          ? `Dry-run reclaim counted ${String((body as { count?: unknown }).count ?? 0)} environments.`
          : `Queued reclaim run ${String((body as { run_id?: unknown }).run_id ?? '')}.`,
      );
      setView(await load());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const replay = async (runId: string) => {
    setBusy(true);
    setNotice('');
    try {
      const base = await discoveryApi.getBaseUrl('proxy');
      const path = replayPath(runId);
      const response = await fetchApi.fetch(`${base}/repave/api/v2${path}`, { method: 'POST' });
      const body = parseJsonBody(await response.text());
      if (!response.ok) {
        throw new Error(parseApiDetail(body, `POST /api/v2${path} returned ${response.status}`));
      }
      setNotice(`Replayed ${runId}.`);
      setView(await load());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Page themeId="tool">
      <Header title="Ops" subtitle="Estate health from GET /api/v2/platform/ops." />
      <Content>
        {error ? <p>{error}</p> : null}
        {notice ? <p>{notice}</p> : null}
        {view === undefined && !error ? <Progress /> : null}
        {view ? (
          <>
            <InfoCard title="Readiness">
              <StructuredMetadataTable
                metadata={{
                  Status: view.ready,
                  'Queued runs': String(view.queuedRuns),
                  'Running runs': String(view.runningRuns),
                  'Queue depth': view.queueDepth,
                  Environments: String(view.environmentCount),
                  'Expired preview': view.reclaimCount,
                }}
              />
              {view.vendingEnabled ? (
                <p>
                  <Button
                    color="primary"
                    variant="outlined"
                    disabled={busy}
                    onClick={() => void reclaimExpired(true)}
                  >
                    Reclaim preview
                  </Button>{' '}
                  <Button
                    color="primary"
                    variant="contained"
                    disabled={busy || !view.asyncEnabled}
                    onClick={() => void reclaimExpired(false)}
                  >
                    Reclaim expired
                  </Button>
                </p>
              ) : (
                <p>Environment vending is not enabled.</p>
              )}
            </InfoCard>
            <Table
              title="Gate toolchain"
              options={{ paging: view.doctor.length > 10, search: false, padding: 'dense' }}
              columns={DOCTOR_COLUMNS}
              data={view.doctor}
              emptyContent={<p>No doctor results.</p>}
            />
            <Table
              title="Dead-letter runs"
              options={{ paging: view.deadLetters.length > 10, search: false, padding: 'dense' }}
              columns={DEAD_LETTER_COLUMNS}
              data={view.deadLetters}
              emptyContent={<p>No dead-letter runs.</p>}
              actions={[
                row => ({
                  icon: () => <Button size="small">Replay</Button>,
                  tooltip: 'Replay',
                  disabled: busy || !canReplayRun(row.status),
                  onClick: () => void replay(row.runId),
                }),
              ]}
            />
          </>
        ) : null}
      </Content>
    </Page>
  );
}
