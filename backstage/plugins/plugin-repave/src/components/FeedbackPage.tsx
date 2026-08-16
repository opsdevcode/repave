import { useCallback, useEffect, useState, type FormEvent } from 'react';
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
import Checkbox from '@material-ui/core/Checkbox';
import FormControlLabel from '@material-ui/core/FormControlLabel';
import TextField from '@material-ui/core/TextField';

export const FRICTION_TAGS = [
  'slow',
  'confusing-form',
  'unclear-errors',
  'missing-docs',
  'gates-heavy',
  'other',
] as const;

export const FEEDBACK_SURFACE = 'backstage';

export type FeedbackEventRow = {
  submittedAt: string;
  csat: number;
  blueprint: string;
  friction: string;
  comment: string;
  actingUser: string;
};

export type FeedbackView = {
  eventCount: number;
  csatAverage: string;
  events: FeedbackEventRow[];
};

export function feedbackQueryDefaults(search: string): { blueprint: string; runId: string } {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  return {
    blueprint: (params.get('blueprint') ?? '').trim(),
    runId: (params.get('run_id') ?? '').trim(),
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

export function formatAverage(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return 'n/a';
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return 'n/a';
  }
  return numeric.toFixed(1);
}

export function rowsFromFeedbackEvents(items: unknown[]): FeedbackEventRow[] {
  return items
    .filter(item => item && typeof item === 'object')
    .map(item => {
      const record = item as Record<string, unknown>;
      const tags = Array.isArray(record.friction_tags)
        ? record.friction_tags.map(tag => String(tag)).filter(Boolean)
        : [];
      return {
        submittedAt: String(record.submitted_at ?? ''),
        csat: Number(record.csat ?? 0),
        blueprint: String(record.blueprint_name ?? ''),
        friction: tags.join(', '),
        comment: String(record.comment ?? ''),
        actingUser: String(record.acting_user ?? ''),
      };
    })
    .filter(row => row.submittedAt);
}

export function parseFeedbackPayload(body: unknown): FeedbackView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const rollup =
    record.rollup && typeof record.rollup === 'object'
      ? (record.rollup as Record<string, unknown>)
      : {};
  const events = Array.isArray(record.events) ? record.events : [];
  return {
    eventCount: Number(rollup.event_count ?? 0),
    csatAverage: formatAverage(rollup.csat_average),
    events: rowsFromFeedbackEvents(events),
  };
}

export function buildFeedbackRequest(input: {
  csat: string;
  blueprint: string;
  blueprintVersion: string;
  comment: string;
  runId: string;
  gatesOutcome: string;
  dryRun: boolean;
  frictionTags: readonly string[];
}): { ok: true; body: Record<string, unknown> } | { ok: false; error: string } {
  const csat = Number.parseInt(input.csat.trim(), 10);
  if (!Number.isInteger(csat) || csat < 1 || csat > 5) {
    return { ok: false, error: 'CSAT must be an integer from 1 to 5' };
  }
  const blueprint = input.blueprint.trim();
  if (!blueprint) {
    return { ok: false, error: 'Blueprint is required' };
  }
  const comment = input.comment.trim();
  if (comment.length > 2000) {
    return { ok: false, error: 'Comment must be at most 2000 characters' };
  }
  const allowed = new Set<string>(FRICTION_TAGS);
  const frictionTags = input.frictionTags.map(tag => tag.trim()).filter(tag => allowed.has(tag));
  const body: Record<string, unknown> = {
    csat,
    blueprint_name: blueprint,
    surface: FEEDBACK_SURFACE,
    dry_run: input.dryRun,
    friction_tags: frictionTags,
  };
  const blueprintVersion = input.blueprintVersion.trim();
  if (blueprintVersion) {
    body.blueprint_version = blueprintVersion;
  }
  if (comment) {
    body.comment = comment;
  }
  const runId = input.runId.trim();
  if (runId) {
    body.run_id = runId;
  }
  const gatesOutcome = input.gatesOutcome.trim();
  if (gatesOutcome) {
    body.gates_outcome = gatesOutcome;
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

const COLUMNS: TableColumn<FeedbackEventRow>[] = [
  { title: 'When', field: 'submittedAt' },
  { title: 'CSAT', field: 'csat' },
  { title: 'Blueprint', field: 'blueprint' },
  { title: 'Friction', field: 'friction' },
  { title: 'Comment', field: 'comment' },
  { title: 'User', field: 'actingUser' },
];

export function FeedbackPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const defaults = feedbackQueryDefaults(window.location.search);
  const [view, setView] = useState<FeedbackView | undefined>();
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
  const [busy, setBusy] = useState(false);
  const [csat, setCsat] = useState('');
  const [blueprint, setBlueprint] = useState(defaults.blueprint);
  const [blueprintVersion, setBlueprintVersion] = useState('');
  const [comment, setComment] = useState('');
  const [runId, setRunId] = useState(defaults.runId);
  const [gatesOutcome, setGatesOutcome] = useState('');
  const [dryRun, setDryRun] = useState(false);
  const [frictionTags, setFrictionTags] = useState<string[]>([]);

  const load = useCallback(async () => {
    const base = await discoveryApi.getBaseUrl('proxy');
    const response = await fetchApi.fetch(`${base}/repave/api/v2/platform/feedback?limit=50`);
    const text = await response.text();
    const body = parseJsonBody(text);
    if (!response.ok) {
      throw new Error(
        parseApiDetail(body, `GET /api/v2/platform/feedback returned ${response.status}`),
      );
    }
    return parseFeedbackPayload(body);
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

  function toggleFriction(tag: string, checked: boolean) {
    setFrictionTags(current => {
      if (checked) {
        return current.includes(tag) ? current : [...current, tag];
      }
      return current.filter(item => item !== tag);
    });
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const request = buildFeedbackRequest({
      csat,
      blueprint,
      blueprintVersion,
      comment,
      runId,
      gatesOutcome,
      dryRun,
      frictionTags,
    });
    if (!request.ok) {
      setFormError(request.error);
      return;
    }
    setBusy(true);
    setFormError('');
    try {
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(`${base}/repave/api/v2/platform/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(request.body),
      });
      const text = await response.text();
      const body = parseJsonBody(text);
      if (!response.ok) {
        throw new Error(
          parseApiDetail(body, `POST /api/v2/platform/feedback returned ${response.status}`),
        );
      }
      setCsat('');
      setComment('');
      setFrictionTags([]);
      setView(await load());
    } catch (err) {
      setFormError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Page themeId="tool">
      <Header
        title="Feedback"
        subtitle="CSAT rollup from GET /api/v2/platform/feedback. Submit records surface=backstage."
      />
      <Content>
        <InfoCard title="Record feedback">
          <form onSubmit={onSubmit}>
            <TextField
              label="CSAT"
              type="number"
              inputProps={{ min: 1, max: 5, step: 1 }}
              value={csat}
              onChange={event => setCsat(event.target.value)}
              helperText="Required — integer from 1 to 5"
              fullWidth
              margin="normal"
              required
            />
            <TextField
              label="Blueprint"
              value={blueprint}
              onChange={event => setBlueprint(event.target.value)}
              helperText="Required — for example terraform-module-generic"
              fullWidth
              margin="normal"
              required
            />
            <TextField
              label="Blueprint version"
              value={blueprintVersion}
              onChange={event => setBlueprintVersion(event.target.value)}
              fullWidth
              margin="normal"
            />
            <TextField
              label="Run id"
              value={runId}
              onChange={event => setRunId(event.target.value)}
              fullWidth
              margin="normal"
            />
            <TextField
              label="Gates outcome"
              value={gatesOutcome}
              onChange={event => setGatesOutcome(event.target.value)}
              helperText="Optional — passed, failed, or skipped"
              fullWidth
              margin="normal"
            />
            <TextField
              label="Comment"
              value={comment}
              onChange={event => setComment(event.target.value)}
              helperText="Optional — at most 2000 characters"
              fullWidth
              margin="normal"
              multiline
              minRows={2}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={dryRun}
                  onChange={event => setDryRun(event.target.checked)}
                  color="primary"
                />
              }
              label="Plan only (dry run)"
            />
            <div>
              {FRICTION_TAGS.map(tag => (
                <FormControlLabel
                  key={tag}
                  control={
                    <Checkbox
                      checked={frictionTags.includes(tag)}
                      onChange={event => toggleFriction(tag, event.target.checked)}
                      color="primary"
                    />
                  }
                  label={tag}
                />
              ))}
            </div>
            <div>
              <Button type="submit" color="primary" variant="contained" disabled={busy}>
                Submit feedback
              </Button>
            </div>
          </form>
        </InfoCard>
        {formError ? <p>{formError}</p> : null}
        {error ? <p>{error}</p> : null}
        {view === undefined && !error ? <Progress /> : null}
        {view ? (
          <>
            <InfoCard title="Rollup">
              <StructuredMetadataTable
                metadata={{
                  Events: String(view.eventCount),
                  'CSAT average': view.csatAverage,
                }}
              />
            </InfoCard>
            <Table
              title="Recent events"
              options={{ paging: view.events.length > 20, search: true, padding: 'dense' }}
              columns={COLUMNS}
              data={view.events}
              emptyContent={<p>No feedback events yet.</p>}
            />
          </>
        ) : null}
      </Content>
    </Page>
  );
}
