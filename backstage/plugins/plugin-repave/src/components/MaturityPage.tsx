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
import TextField from '@material-ui/core/TextField';

export type MaturityLevelRow = {
  level: number;
  count: number;
};

export type MaturityEntityRow = {
  entityId: string;
  displayName: string;
  owner: string;
  maturityLevel: number;
  maturityLabel: string;
};

export type MaturityView = {
  catalogEnabled: boolean;
  entityCount: number;
  averageLevel: string;
  byLevel: MaturityLevelRow[];
  bottom: MaturityEntityRow[];
};

export type InitiativeRow = {
  id: string;
  title: string;
  description: string;
  owningTeam: string;
  dueDate: string;
  targetLevel: number;
  targetRuleKeys: string;
  passed: number;
  total: number;
  ratio: string;
  overdue: boolean;
};

export type InactiveInitiativeRow = {
  id: string;
  title: string;
  owningTeam: string;
  dueDate: string;
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

export function formatRatio(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return 'n/a';
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return 'n/a';
  }
  return `${Math.round(numeric * 1000) / 10}%`;
}

export function parseMaturityPayload(body: unknown): MaturityView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const byLevel = Array.isArray(record.by_level)
    ? record.by_level
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const row = item as Record<string, unknown>;
          return { level: Number(row.level ?? 0), count: Number(row.count ?? 0) };
        })
    : [];
  const bottom = Array.isArray(record.bottom_entities)
    ? record.bottom_entities
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const row = item as Record<string, unknown>;
          return {
            entityId: String(row.entity_id ?? ''),
            displayName: String(row.display_name ?? row.entity_id ?? ''),
            owner: String(row.owner ?? ''),
            maturityLevel: Number(row.maturity_level ?? 0),
            maturityLabel: String(row.maturity_label ?? ''),
          };
        })
        .filter(row => row.entityId)
    : [];
  const average = Number(record.average_level ?? 0);
  return {
    catalogEnabled: Boolean(record.catalog_enabled),
    entityCount: Number(record.entity_count ?? 0),
    averageLevel: Number.isFinite(average) ? average.toFixed(1) : '0.0',
    byLevel,
    bottom,
  };
}

export function rowsFromInitiatives(items: unknown[]): InitiativeRow[] {
  return items
    .filter(item => item && typeof item === 'object')
    .map(item => {
      const record = item as Record<string, unknown>;
      const initiative =
        record.initiative && typeof record.initiative === 'object'
          ? (record.initiative as Record<string, unknown>)
          : {};
      const rules = Array.isArray(initiative.target_rule_keys)
        ? initiative.target_rule_keys.map(key => String(key).trim()).filter(Boolean)
        : String(initiative.target_rule_keys ?? '')
            .split(',')
            .map(key => key.trim())
            .filter(Boolean);
      return {
        id: String(initiative.id ?? ''),
        title: String(initiative.title ?? ''),
        description: String(initiative.description ?? ''),
        owningTeam: String(initiative.owning_team ?? ''),
        dueDate: String(initiative.due_date ?? ''),
        targetLevel: Number(initiative.target_level ?? 0),
        targetRuleKeys: rules.join(', '),
        passed: Number(record.passed ?? 0),
        total: Number(record.total ?? 0),
        ratio: formatRatio(record.ratio),
        overdue: Boolean(record.overdue),
      };
    })
    .filter(row => row.id);
}

export function parseInitiativesPayload(body: unknown): InitiativeRow[] {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const items = Array.isArray(record.initiatives) ? record.initiatives : [];
  return rowsFromInitiatives(items);
}

export function parseInactiveInitiatives(body: unknown): InactiveInitiativeRow[] {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const items = Array.isArray(record.inactive) ? record.inactive : [];
  return items
    .filter(item => item && typeof item === 'object')
    .map(item => {
      const row = item as Record<string, unknown>;
      return {
        id: String(row.id ?? ''),
        title: String(row.title ?? ''),
        owningTeam: String(row.owning_team ?? ''),
        dueDate: String(row.due_date ?? ''),
      };
    })
    .filter(row => row.id);
}

export function parseRuleKeys(value: string): string[] {
  return value
    .split(',')
    .map(item => item.trim())
    .filter(Boolean);
}

export function buildCreateInitiativeRequest(input: {
  title: string;
  description: string;
  owningTeam: string;
  dueDate: string;
  targetLevel: string;
  targetRuleKeys: string;
}): { ok: true; body: Record<string, unknown> } | { ok: false; error: string } {
  const title = input.title.trim();
  if (!title) {
    return { ok: false, error: 'Title is required' };
  }
  const body: Record<string, unknown> = { title };
  const description = input.description.trim();
  if (description) {
    body.description = description;
  }
  const owningTeam = input.owningTeam.trim();
  if (owningTeam) {
    body.owning_team = owningTeam;
  }
  const dueDate = input.dueDate.trim();
  if (dueDate) {
    body.due_date = dueDate;
  }
  const levelRaw = input.targetLevel.trim();
  if (levelRaw) {
    const level = Number(levelRaw);
    if (!Number.isInteger(level) || level < 0) {
      return { ok: false, error: 'Target level must be a whole number' };
    }
    body.target_level = level;
  }
  const rules = parseRuleKeys(input.targetRuleKeys);
  if (rules.length) {
    body.target_rule_keys = rules;
  }
  return { ok: true, body };
}

export function buildPatchInitiativeRequest(input: {
  title: string;
  description: string;
  owningTeam: string;
  dueDate: string;
  targetLevel: string;
  targetRuleKeys: string;
  active?: boolean;
}): { ok: true; body: Record<string, unknown> } | { ok: false; error: string } {
  const created = buildCreateInitiativeRequest(input);
  if (!created.ok) {
    return created;
  }
  if (input.active !== undefined) {
    return { ok: true, body: { ...created.body, active: input.active } };
  }
  return created;
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

const LEVEL_COLUMNS: TableColumn<MaturityLevelRow>[] = [
  { title: 'Level', field: 'level' },
  { title: 'Services', field: 'count' },
];

const BOTTOM_COLUMNS: TableColumn<MaturityEntityRow>[] = [
  { title: 'Service', field: 'displayName' },
  { title: 'Owner', field: 'owner' },
  { title: 'Level', field: 'maturityLevel' },
  { title: 'Label', field: 'maturityLabel' },
];

const INITIATIVE_COLUMNS: TableColumn<InitiativeRow>[] = [
  { title: 'Initiative', field: 'title' },
  { title: 'Team', field: 'owningTeam' },
  { title: 'Target', field: 'targetLevel' },
  { title: 'Passed', field: 'passed' },
  { title: 'Total', field: 'total' },
  { title: 'Progress', field: 'ratio' },
  {
    title: 'Due',
    field: 'overdue',
    render: row => (row.overdue ? 'Overdue' : row.dueDate),
  },
];

const INACTIVE_COLUMNS: TableColumn<InactiveInitiativeRow>[] = [
  { title: 'Initiative', field: 'title' },
  { title: 'Team', field: 'owningTeam' },
  { title: 'Due', field: 'dueDate' },
];

const emptyForm = {
  title: '',
  description: '',
  owningTeam: '',
  dueDate: '',
  targetLevel: '',
  targetRuleKeys: '',
};

export function MaturityPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [maturity, setMaturity] = useState<MaturityView | undefined>();
  const [initiatives, setInitiatives] = useState<InitiativeRow[] | undefined>();
  const [inactive, setInactive] = useState<InactiveInitiativeRow[]>([]);
  const [maturityError, setMaturityError] = useState('');
  const [initiativeError, setInitiativeError] = useState('');
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState('');
  const [busy, setBusy] = useState(false);
  const [actionMessage, setActionMessage] = useState('');

  const load = useCallback(async () => {
    const base = await discoveryApi.getBaseUrl('proxy');
    const [maturityResponse, initiativeResponse] = await Promise.all([
      fetchApi.fetch(`${base}/repave/api/v2/platform/maturity`),
      fetchApi.fetch(`${base}/repave/api/v2/platform/initiatives`),
    ]);
    const maturityText = await maturityResponse.text();
    const initiativeText = await initiativeResponse.text();
    const maturityBody = parseJsonBody(maturityText);
    const initiativeBody = parseJsonBody(initiativeText);
    return {
      maturityOk: maturityResponse.ok,
      initiativeOk: initiativeResponse.ok,
      maturityBody,
      initiativeBody,
      maturityStatus: maturityResponse.status,
      initiativeStatus: initiativeResponse.status,
    };
  }, [discoveryApi, fetchApi]);

  const applyLoad = useCallback(
    (next: Awaited<ReturnType<typeof load>>) => {
      if (next.maturityOk) {
        setMaturity(parseMaturityPayload(next.maturityBody));
        setMaturityError('');
      } else {
        setMaturity(undefined);
        setMaturityError(
          parseApiDetail(
            next.maturityBody,
            `GET /api/v2/platform/maturity returned ${next.maturityStatus}`,
          ),
        );
      }
      if (next.initiativeOk) {
        setInitiatives(parseInitiativesPayload(next.initiativeBody));
        setInactive(parseInactiveInitiatives(next.initiativeBody));
        setInitiativeError('');
      } else {
        setInitiatives(undefined);
        setInactive([]);
        setInitiativeError(
          parseApiDetail(
            next.initiativeBody,
            `GET /api/v2/platform/initiatives returned ${next.initiativeStatus}`,
          ),
        );
      }
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    load()
      .then(next => {
        if (!cancelled) {
          applyLoad(next);
        }
      })
      .catch(err => {
        if (!cancelled) {
          setMaturityError(err instanceof Error ? err.message : String(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [load, applyLoad]);

  async function refreshInitiatives() {
    const next = await load();
    applyLoad(next);
  }

  async function postJson(path: string, method: 'POST' | 'PATCH' | 'DELETE', body?: unknown) {
    const base = await discoveryApi.getBaseUrl('proxy');
    const response = await fetchApi.fetch(`${base}/repave/api/v2${path}`, {
      method,
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await response.text();
    const parsed = parseJsonBody(text);
    if (!response.ok) {
      throw new Error(parseApiDetail(parsed, `${method} /api/v2${path} returned ${response.status}`));
    }
  }

  async function onSave(event: FormEvent) {
    event.preventDefault();
    const request = editingId
      ? buildPatchInitiativeRequest(form)
      : buildCreateInitiativeRequest(form);
    if (!request.ok) {
      setActionMessage(request.error);
      return;
    }
    setBusy(true);
    setActionMessage('');
    try {
      if (editingId) {
        await postJson(`/platform/initiatives/${encodeURIComponent(editingId)}`, 'PATCH', request.body);
        setActionMessage(`Updated ${editingId}`);
      } else {
        await postJson('/platform/initiatives', 'POST', request.body);
        setActionMessage(`Created ${String(request.body.title)}`);
      }
      setForm(emptyForm);
      setEditingId('');
      await refreshInitiatives();
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function startEdit(row: InitiativeRow) {
    setEditingId(row.id);
    setForm({
      title: row.title,
      description: row.description,
      owningTeam: row.owningTeam,
      dueDate: row.dueDate,
      targetLevel: row.targetLevel ? String(row.targetLevel) : '',
      targetRuleKeys: row.targetRuleKeys,
    });
    setActionMessage('');
  }

  async function onDeactivate(row: InitiativeRow) {
    setBusy(true);
    setActionMessage('');
    try {
      await postJson(`/platform/initiatives/${encodeURIComponent(row.id)}`, 'DELETE');
      setActionMessage(`Deactivated ${row.title}`);
      if (editingId === row.id) {
        setEditingId('');
        setForm(emptyForm);
      }
      await refreshInitiatives();
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onReactivate(row: InactiveInitiativeRow) {
    setBusy(true);
    setActionMessage('');
    try {
      await postJson(`/platform/initiatives/${encodeURIComponent(row.id)}`, 'PATCH', {
        active: true,
      });
      setActionMessage(`Reactivated ${row.title}`);
      await refreshInitiatives();
    } catch (err) {
      setActionMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const loading = maturity === undefined && !maturityError && initiatives === undefined && !initiativeError;

  const initiativeColumns: TableColumn<InitiativeRow>[] = [
    ...INITIATIVE_COLUMNS,
    {
      title: '',
      field: 'id',
      sorting: false,
      searchable: false,
      render: row => (
        <>
          <Button size="small" disabled={busy} onClick={() => startEdit(row)}>
            Edit
          </Button>
          <Button
            size="small"
            disabled={busy}
            onClick={() => {
              void onDeactivate(row);
            }}
          >
            Deactivate
          </Button>
        </>
      ),
    },
  ];

  const inactiveColumns: TableColumn<InactiveInitiativeRow>[] = [
    ...INACTIVE_COLUMNS,
    {
      title: '',
      field: 'id',
      sorting: false,
      searchable: false,
      render: row => (
        <Button
          size="small"
          disabled={busy}
          onClick={() => {
            void onReactivate(row);
          }}
        >
          Reactivate
        </Button>
      ),
    },
  ];

  return (
    <Page themeId="tool">
      <Header
        title="Maturity"
        subtitle="Catalog maturity and initiatives from /api/v2/platform. Create, edit, and deactivate need admin."
      />
      <Content>
        {maturityError ? <p>{maturityError}</p> : null}
        {initiativeError ? <p>{initiativeError}</p> : null}
        {actionMessage ? <p>{actionMessage}</p> : null}
        {loading ? <Progress /> : null}
        {maturity ? (
          <>
            <InfoCard title="Distribution">
              <StructuredMetadataTable
                metadata={{
                  Services: String(maturity.entityCount),
                  'Average level': maturity.averageLevel,
                  Catalog: maturity.catalogEnabled ? 'On' : 'Off',
                }}
              />
            </InfoCard>
            <Table
              title="By level"
              options={{ paging: false, search: false, padding: 'dense' }}
              columns={LEVEL_COLUMNS}
              data={maturity.byLevel}
              emptyContent={<p>No maturity levels yet.</p>}
            />
            <Table
              title="Lowest services"
              options={{ paging: maturity.bottom.length > 10, search: true, padding: 'dense' }}
              columns={BOTTOM_COLUMNS}
              data={maturity.bottom}
              emptyContent={<p>No catalog entities yet.</p>}
            />
          </>
        ) : null}
        {initiatives ? (
          <Table
            title="Initiatives"
            options={{ paging: initiatives.length > 10, search: true, padding: 'dense' }}
            columns={initiativeColumns}
            data={initiatives}
            emptyContent={<p>No active initiatives.</p>}
          />
        ) : null}
        {inactive.length ? (
          <Table
            title="Inactive"
            options={{ paging: inactive.length > 10, search: true, padding: 'dense' }}
            columns={inactiveColumns}
            data={inactive}
          />
        ) : null}
        {initiatives !== undefined ? (
          <InfoCard title={editingId ? `Edit ${editingId}` : 'Create initiative'}>
            <form onSubmit={onSave}>
              <TextField
                label="Title"
                value={form.title}
                onChange={event => setForm(current => ({ ...current, title: event.target.value }))}
                helperText="Required"
                fullWidth
                margin="normal"
              />
              <TextField
                label="Description"
                value={form.description}
                onChange={event =>
                  setForm(current => ({ ...current, description: event.target.value }))
                }
                fullWidth
                margin="normal"
              />
              <TextField
                label="Owning team"
                value={form.owningTeam}
                onChange={event =>
                  setForm(current => ({ ...current, owningTeam: event.target.value }))
                }
                fullWidth
                margin="normal"
              />
              <TextField
                label="Due date"
                value={form.dueDate}
                onChange={event => setForm(current => ({ ...current, dueDate: event.target.value }))}
                helperText="Optional YYYY-MM-DD"
                fullWidth
                margin="normal"
              />
              <TextField
                label="Target maturity level"
                value={form.targetLevel}
                onChange={event =>
                  setForm(current => ({ ...current, targetLevel: event.target.value }))
                }
                helperText="Optional whole number"
                fullWidth
                margin="normal"
              />
              <TextField
                label="Target rule keys"
                value={form.targetRuleKeys}
                onChange={event =>
                  setForm(current => ({ ...current, targetRuleKeys: event.target.value }))
                }
                helperText="Optional comma-separated scorecard keys"
                fullWidth
                margin="normal"
              />
              <Button type="submit" color="primary" variant="contained" disabled={busy}>
                {editingId ? 'Save changes' : 'Create initiative'}
              </Button>
              {editingId ? (
                <Button
                  disabled={busy}
                  onClick={() => {
                    setEditingId('');
                    setForm(emptyForm);
                  }}
                >
                  Cancel
                </Button>
              ) : null}
            </form>
          </InfoCard>
        ) : null}
      </Content>
    </Page>
  );
}
