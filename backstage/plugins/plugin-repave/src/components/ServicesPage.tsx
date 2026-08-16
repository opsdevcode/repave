import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  Content,
  Header,
  InfoCard,
  Link,
  Page,
  Progress,
  StructuredMetadataTable,
} from '@backstage/core-components';
import { discoveryApiRef, fetchApiRef, useApi } from '@backstage/core-plugin-api';
import Button from '@material-ui/core/Button';
import TextField from '@material-ui/core/TextField';
import { queryParam } from './queryParam';

export type ServiceView = {
  entityId: string;
  displayName: string;
  owner: string;
  blueprint: string;
  maturity: string;
  cost: string;
  slo: string;
  deployment: string;
  lineage: string;
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

export function servicesPath(entityId: string): string {
  const value = entityId.trim();
  return value ? `/services?entity=${encodeURIComponent(value)}` : '/services';
}

export function buildLivePlanBody(entityId: string): Record<string, unknown> {
  return { kind: 'live_plan', entity_id: entityId.trim() };
}

export function parseServiceDetail(body: unknown): ServiceView | undefined {
  if (!body || typeof body !== 'object') {
    return undefined;
  }
  const record = body as Record<string, unknown>;
  const entityId = String(record.entity_id ?? '');
  if (!entityId) {
    return undefined;
  }
  const maturity =
    record.maturity && typeof record.maturity === 'object'
      ? (record.maturity as Record<string, unknown>)
      : {};
  let cost: Record<string, unknown> = {};
  if (record.cost_actuals && typeof record.cost_actuals === 'object') {
    cost = record.cost_actuals as Record<string, unknown>;
  } else if (record.cost_estimate && typeof record.cost_estimate === 'object') {
    cost = record.cost_estimate as Record<string, unknown>;
  }
  const slo =
    record.slo_summary && typeof record.slo_summary === 'object'
      ? (record.slo_summary as Record<string, unknown>)
      : {};
  const deployment =
    record.deployment_status && typeof record.deployment_status === 'object'
      ? (record.deployment_status as Record<string, unknown>)
      : {};
  const scorecard = Array.isArray(record.scorecard) ? record.scorecard : [];
  return {
    entityId,
    displayName: String(record.display_name ?? entityId),
    owner: String(record.owner ?? ''),
    blueprint: String(record.blueprint_name ?? ''),
    maturity: String(maturity.label ?? maturity.level ?? ''),
    cost: String(cost.monthly_usd ?? cost.amount ?? record.cost_badge ?? ''),
    slo: String(slo.status ?? slo.summary ?? ''),
    deployment: String(deployment.status ?? deployment.phase ?? ''),
    lineage: scorecard.length ? `${scorecard.length} scorecard dimensions` : '',
  };
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

export function ServicesPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [entityId, setEntityId] = useState(() => queryParam(window.location.search, 'entity'));
  const [view, setView] = useState<ServiceView | undefined>();
  const [error, setError] = useState('');
  const [planError, setPlanError] = useState('');
  const [planRunId, setPlanRunId] = useState('');
  const [busy, setBusy] = useState(false);

  const loadEntity = useCallback(
    async (nextId: string) => {
      if (!nextId) {
        return undefined;
      }
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(
        `${base}/repave/api/v2/catalog/entities/${encodeURIComponent(nextId)}`,
      );
      const text = await response.text();
      const body = parseJsonBody(text);
      if (!response.ok) {
        throw new Error(
          parseApiDetail(body, `GET /api/v2/catalog/entities/${nextId} returned ${response.status}`),
        );
      }
      return parseServiceDetail(body);
    },
    [discoveryApi, fetchApi],
  );

  useEffect(() => {
    let cancelled = false;
    if (!entityId) {
      setView(undefined);
      return () => {
        cancelled = true;
      };
    }
    loadEntity(entityId)
      .then(next => {
        if (!cancelled) {
          setView(next);
          setError('');
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
  }, [entityId, loadEntity]);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const next = entityId.trim();
    setEntityId(next);
    window.history.replaceState(null, '', servicesPath(next));
  }

  async function onLivePlan() {
    if (!view) {
      return;
    }
    setBusy(true);
    setPlanError('');
    setPlanRunId('');
    try {
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(`${base}/repave/api/v2/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(buildLivePlanBody(view.entityId)),
      });
      const text = await response.text();
      const body = parseJsonBody(text);
      if (!response.ok) {
        throw new Error(parseApiDetail(body, `POST /api/v2/runs returned ${response.status}`));
      }
      const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
      const runId = String(record.run_id ?? '');
      if (!runId) {
        throw new Error('POST /api/v2/runs did not return run_id');
      }
      setPlanRunId(runId);
    } catch (err) {
      setPlanError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page themeId="tool">
      <Header
        title="Services"
        subtitle="Catalog entity detail. Live plan enqueues a worker-only terraform plan."
      />
      <Content>
        <form onSubmit={onSubmit}>
          <TextField
            label="Entity id"
            value={entityId}
            onChange={event => setEntityId(event.target.value)}
            helperText="Uses GET /api/v2/catalog/entities/{entity_id}"
          />
          <Button color="primary" type="submit">
            Load entity
          </Button>
        </form>
        {error ? <p>{error}</p> : null}
        {entityId && view === undefined && !error ? <Progress /> : null}
        {view ? (
          <InfoCard title={view.displayName}>
            <StructuredMetadataTable
              dense
              metadata={{
                Entity: view.entityId,
                Owner: view.owner,
                Blueprint: view.blueprint,
                Maturity: view.maturity || 'n/a',
                Cost: view.cost || 'n/a',
                SLO: view.slo || 'n/a',
                Deployment: view.deployment || 'n/a',
                Lineage: view.lineage || 'n/a',
              }}
            />
            <Button
              color="primary"
              variant="contained"
              disabled={busy}
              onClick={() => {
                void onLivePlan();
              }}
            >
              Run live plan
            </Button>
            {planError ? <p>{planError}</p> : null}
            {planRunId ? (
              <p>
                Queued{' '}
                <Link to={`/run-console?run=${encodeURIComponent(planRunId)}`}>{planRunId}</Link>
              </p>
            ) : null}
          </InfoCard>
        ) : null}
      </Content>
    </Page>
  );
}
