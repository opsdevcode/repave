import { useEffect, useMemo, useState, type FormEvent } from 'react';
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
import MenuItem from '@material-ui/core/MenuItem';
import TextField from '@material-ui/core/TextField';

function placeholderMatches(text: string): RegExpMatchArray[] {
  return [...text.matchAll(/\{([a-z][a-z0-9_]*)\}/g)];
}
const NON_SLUG = /[^a-z0-9]+/g;
const UNDERSCORE_NAME_FIELDS = new Set([
  'role_name',
  'collection_name',
  'sample_role_name',
  'namespace',
]);

export type BlueprintInput = {
  name: string;
  type: string;
  required: boolean;
  description: string;
  defaultValue: string;
  enumValues: string[];
  multi: boolean;
  advanced: boolean;
  guidedFrom: string;
};

export type BlueprintRow = {
  name: string;
  version: string;
  description: string;
  artifactType: string;
  family: string;
  familyTitle: string;
  inputs: BlueprintInput[];
};

export type BlueprintFamily = {
  family: string;
  title: string;
  subtitle: string;
  count: number;
};

export type BlueprintCatalog = {
  families: BlueprintFamily[];
  rows: BlueprintRow[];
};

export type GenerateResultView = {
  blueprint: string;
  gatesOutcome: string;
  gatesPassed: boolean;
  fileCount: number;
  gates: { name: string; passed: boolean; skipped: boolean; message: string }[];
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

export function scaffolderHref(): string {
  return '/create';
}

export function parseBlueprintInput(raw: unknown): BlueprintInput | undefined {
  if (!raw || typeof raw !== 'object') {
    return undefined;
  }
  const record = raw as Record<string, unknown>;
  const name = String(record.name ?? '').trim();
  if (!name) {
    return undefined;
  }
  const enumValues = Array.isArray(record.enum)
    ? record.enum.map(item => String(item)).filter(Boolean)
    : [];
  return {
    name,
    type: String(record.type ?? 'string'),
    required: Boolean(record.required),
    description: String(record.description ?? ''),
    defaultValue: record.default === undefined || record.default === null ? '' : String(record.default),
    enumValues,
    multi: Boolean(record.multi),
    advanced: Boolean(record.advanced),
    guidedFrom: String(record.guided_from ?? ''),
  };
}

export function slugifyIdentity(value: string, separator = '-'): string {
  const text = value.trim().toLowerCase().replace(/\/+$/, '');
  const leaf = text.includes('/') ? text.slice(text.lastIndexOf('/') + 1) : text;
  const parts = leaf
    .replace(/,/g, ' ')
    .split(/\s+/)
    .map(part => part.trim())
    .filter(Boolean);
  const slugs: string[] = [];
  for (const part of parts) {
    const slug = part
      .replace(NON_SLUG, separator)
      .replace(new RegExp(`${separator}{2,}`, 'g'), separator)
      .replace(new RegExp(`^${separator}|${separator}$`, 'g'), '');
    if (slug) {
      slugs.push(slug);
    }
  }
  return slugs.join(separator);
}

export function humanizeIdentity(value: string): string {
  const text = value.trim();
  if (!text) {
    return '';
  }
  const parts = text
    .split(',')
    .map(part => part.trim())
    .filter(Boolean);
  if (parts.length > 1) {
    return parts.join(', ');
  }
  return text.replace(/[_-]/g, ' ');
}

export function renderGuidedFrom(
  template: string,
  values: Record<string, string>,
  options: { slug: boolean; separator: string },
): string {
  const text = template.trim();
  if (!text) {
    return '';
  }
  let cursor = 0;
  const parts: string[] = [];
  for (const match of placeholderMatches(text)) {
    const key = match[1] ?? '';
    const raw = (values[key] ?? '').trim();
    if (!raw || match.index === undefined) {
      return '';
    }
    parts.push(text.slice(cursor, match.index));
    parts.push(
      options.slug
        ? slugifyIdentity(raw, options.separator)
        : humanizeIdentity(raw),
    );
    cursor = match.index + match[0].length;
  }
  parts.push(text.slice(cursor));
  const rendered = parts.join('').trim();
  if (!rendered) {
    return '';
  }
  if (options.slug) {
    return slugifyIdentity(rendered, options.separator);
  }
  return rendered.replace(/\s+/g, ' ');
}

export function applyGuidedIdentity(
  inputs: BlueprintInput[],
  values: Record<string, string>,
): Record<string, string> {
  const next = { ...values };
  for (let pass = 0; pass < 2; pass += 1) {
    for (const field of inputs) {
      if (!field.guidedFrom || !field.required) {
        continue;
      }
      if ((next[field.name] ?? '').trim()) {
        continue;
      }
      const separator = UNDERSCORE_NAME_FIELDS.has(field.name) ? '_' : '-';
      const rendered = renderGuidedFrom(field.guidedFrom, next, {
        slug: field.name !== 'description',
        separator,
      });
      if (rendered) {
        next[field.name] = rendered;
      }
    }
  }
  return next;
}

export function visibleInputs(
  inputs: BlueprintInput[],
  showAdvanced: boolean,
): BlueprintInput[] {
  return inputs.filter(input => {
    if (input.guidedFrom) {
      return false;
    }
    if (input.advanced && !showAdvanced) {
      return false;
    }
    return true;
  });
}

export function defaultInputValues(inputs: BlueprintInput[]): Record<string, string> {
  const values: Record<string, string> = {};
  for (const input of inputs) {
    values[input.name] = input.defaultValue;
  }
  return values;
}

export function buildGenerateRequest(input: {
  blueprint: string;
  values: Record<string, string>;
  inputs: BlueprintInput[];
  dryRun: boolean;
}): { ok: true; body: Record<string, unknown> } | { ok: false; error: string } {
  const blueprint = input.blueprint.trim();
  if (!blueprint) {
    return { ok: false, error: 'Pick a blueprint' };
  }
  const filled = applyGuidedIdentity(input.inputs, input.values);
  for (const field of input.inputs) {
    if (!field.required) {
      continue;
    }
    if ((filled[field.name] ?? '').trim()) {
      continue;
    }
    if (field.guidedFrom) {
      const needed = placeholderMatches(field.guidedFrom)
        .map(match => match[1])
        .filter(Boolean)
        .join(', ');
      return {
        ok: false,
        error: needed
          ? `Set ${needed} so ${field.name} can be filled`
          : `${field.name} is required`,
      };
    }
    return { ok: false, error: `${field.name} is required` };
  }
  const inputs: Record<string, string> = {};
  for (const [key, value] of Object.entries(filled)) {
    const trimmed = value.trim();
    if (trimmed) {
      inputs[key] = trimmed;
    }
  }
  return {
    ok: true,
    body: {
      blueprint,
      dry_run: input.dryRun,
      inputs,
    },
  };
}

export function gateStatus(gate: {
  skipped: boolean;
  passed: boolean;
}): string {
  if (gate.skipped) {
    return 'skipped';
  }
  if (gate.passed) {
    return 'passed';
  }
  return 'failed';
}

export function parseGenerateResult(body: unknown): GenerateResultView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const gates = Array.isArray(record.gates)
    ? record.gates
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
        .filter(gate => gate.name)
    : [];
  const files = record.rendered_files;
  let fileCount = 0;
  if (Array.isArray(files)) {
    fileCount = files.length;
  } else if (Number.isFinite(Number(files))) {
    fileCount = Number(files);
  }
  return {
    blueprint: String(record.blueprint ?? ''),
    gatesOutcome: String(record.gates_outcome ?? ''),
    gatesPassed: Boolean(record.gates_passed),
    fileCount,
    gates,
  };
}

export function parseBlueprintCatalog(body: unknown): BlueprintCatalog {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const groups = Array.isArray(record.groups) ? record.groups : [];
  const families: BlueprintFamily[] = [];
  const rows: BlueprintRow[] = [];
  for (const item of groups) {
    if (!item || typeof item !== 'object') {
      continue;
    }
    const group = item as Record<string, unknown>;
    const family = String(group.family ?? '');
    const title = String(group.title ?? family);
    const blueprints = Array.isArray(group.blueprints) ? group.blueprints : [];
    if (!family) {
      continue;
    }
    const start = rows.length;
    for (const raw of blueprints) {
      if (!raw || typeof raw !== 'object') {
        continue;
      }
      const blueprint = raw as Record<string, unknown>;
      const name = String(blueprint.name ?? '');
      if (!name) {
        continue;
      }
      const inputs = Array.isArray(blueprint.inputs)
        ? blueprint.inputs
            .map(parseBlueprintInput)
            .filter((field): field is BlueprintInput => Boolean(field))
        : [];
      rows.push({
        name,
        version: String(blueprint.version ?? ''),
        description: String(blueprint.description ?? ''),
        artifactType: String(blueprint.artifact_type ?? ''),
        family,
        familyTitle: title,
        inputs,
      });
    }
    families.push({
      family,
      title,
      subtitle: String(group.subtitle ?? ''),
      count: rows.length - start,
    });
  }
  return { families, rows };
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

const COLUMNS: TableColumn<BlueprintRow>[] = [
  { title: 'Blueprint', field: 'name' },
  { title: 'Family', field: 'familyTitle' },
  { title: 'Type', field: 'artifactType' },
  { title: 'Version', field: 'version' },
  { title: 'Description', field: 'description' },
];

export function GeneratePage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [catalog, setCatalog] = useState<BlueprintCatalog | undefined>();
  const [error, setError] = useState('');
  const [selected, setSelected] = useState('');
  const [values, setValues] = useState<Record<string, string>>({});
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [dryRun, setDryRun] = useState(true);
  const [busy, setBusy] = useState(false);
  const [submitMessage, setSubmitMessage] = useState('');
  const [result, setResult] = useState<GenerateResultView | undefined>();

  const selectedRow = useMemo(
    () => catalog?.rows.find(row => row.name === selected),
    [catalog, selected],
  );
  const fields = selectedRow ? visibleInputs(selectedRow.inputs, showAdvanced) : [];

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(`${base}/repave/api/v2/catalog/blueprints`);
      const text = await response.text();
      const body = parseJsonBody(text);
      if (!response.ok) {
        throw new Error(
          parseApiDetail(body, `GET /api/v2/catalog/blueprints returned ${response.status}`),
        );
      }
      return parseBlueprintCatalog(body);
    };
    load()
      .then(next => {
        if (!cancelled) {
          setCatalog(next);
          setError('');
          if (next.rows[0]) {
            setSelected(next.rows[0].name);
            setValues(defaultInputValues(next.rows[0].inputs));
          }
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

  function selectBlueprint(name: string) {
    const row = catalog?.rows.find(item => item.name === name);
    setSelected(name);
    setValues(row ? defaultInputValues(row.inputs) : {});
    setSubmitMessage('');
    setResult(undefined);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const request = buildGenerateRequest({
      blueprint: selected,
      values,
      inputs: selectedRow?.inputs ?? [],
      dryRun,
    });
    if (!request.ok) {
      setSubmitMessage(request.error);
      setResult(undefined);
      return;
    }
    setBusy(true);
    setSubmitMessage('');
    setResult(undefined);
    try {
      const base = await discoveryApi.getBaseUrl('proxy');
      const response = await fetchApi.fetch(`${base}/repave/api/v2/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(request.body),
      });
      const text = await response.text();
      const body = parseJsonBody(text);
      if (!response.ok) {
        throw new Error(
          parseApiDetail(body, `POST /api/v2/generate returned ${response.status}`),
        );
      }
      const parsed = parseGenerateResult(body);
      setResult(parsed);
      const mode = dryRun ? 'Dry-run' : 'Generate';
      setSubmitMessage(
        parsed.gatesOutcome ? `${mode} ${parsed.gatesOutcome}` : `${mode} completed`,
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
        title="Generate"
        subtitle="Pick a governed blueprint, fill inputs, and dry-run generate over /api/v2."
      />
      <Content>
        {error ? <p>{error}</p> : null}
        {catalog === undefined && !error ? <Progress /> : null}
        {catalog ? (
          <>
            {catalog.families.map(family => (
              <InfoCard key={family.family} title={`${family.title} (${family.count})`}>
                <p>{family.subtitle}</p>
              </InfoCard>
            ))}
            <Table
              options={{ paging: catalog.rows.length > 20, search: true, padding: 'dense' }}
              columns={COLUMNS}
              data={catalog.rows}
              onRowClick={(_event, row) => {
                if (row) {
                  selectBlueprint(row.name);
                }
              }}
              emptyContent={<p>No blueprints in the catalog.</p>}
            />
            {selectedRow ? (
              <InfoCard title={`Generate ${selectedRow.name}`}>
                <form onSubmit={onSubmit}>
                  <p>
                    Selected blueprint: <strong>{selectedRow.name}</strong> (
                    {selectedRow.version || 'unversioned'})
                  </p>
                  {selectedRow.inputs.some(input => input.guidedFrom) ? (
                    <p>
                      Name and description fill from your selections. Scaffolder{' '}
                      <Link to={scaffolderHref()}>Create</Link> still works for the
                      same <code>POST /api/v2/generate</code> contract.
                    </p>
                  ) : (
                    <p>
                      Scaffolder <Link to={scaffolderHref()}>Create</Link> remains
                      available for the same API.
                    </p>
                  )}
                  {fields.map(field =>
                    field.enumValues.length ? (
                      <TextField
                        key={field.name}
                        select
                        label={field.name}
                        value={values[field.name] ?? ''}
                        onChange={event =>
                          setValues(current => ({
                            ...current,
                            [field.name]: event.target.value,
                          }))
                        }
                        helperText={field.description}
                        fullWidth
                        margin="normal"
                        required={field.required}
                      >
                        {field.enumValues.map(option => (
                          <MenuItem key={option} value={option}>
                            {option}
                          </MenuItem>
                        ))}
                      </TextField>
                    ) : (
                      <TextField
                        key={field.name}
                        label={field.name}
                        value={values[field.name] ?? ''}
                        onChange={event =>
                          setValues(current => ({
                            ...current,
                            [field.name]: event.target.value,
                          }))
                        }
                        helperText={field.description}
                        fullWidth
                        margin="normal"
                        required={field.required && !field.defaultValue}
                        multiline={field.multi}
                        minRows={field.multi ? 3 : 1}
                      />
                    ),
                  )}
                  {selectedRow.inputs.some(input => input.advanced) ? (
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={showAdvanced}
                          onChange={event => setShowAdvanced(event.target.checked)}
                          color="primary"
                        />
                      }
                      label="Show advanced inputs"
                    />
                  ) : null}
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={dryRun}
                        onChange={event => setDryRun(event.target.checked)}
                        color="primary"
                      />
                    }
                    label="Dry-run (plan only; no GitHub PR)"
                  />
                  <div>
                    <Button type="submit" color="primary" variant="contained" disabled={busy}>
                      {dryRun ? 'Dry-run generate' : 'Generate'}
                    </Button>
                  </div>
                  {submitMessage ? <p>{submitMessage}</p> : null}
                  {result ? (
                    <div>
                      <p>
                        Gates: <strong>{result.gatesOutcome || 'unknown'}</strong>
                        {result.fileCount
                          ? ` · ${result.fileCount} rendered file${
                              result.fileCount === 1 ? '' : 's'
                            }`
                          : ''}
                      </p>
                      {result.gates.length ? (
                        <ul>
                          {result.gates.map(gate => (
                            <li key={gate.name}>
                              {gate.name}: {gateStatus(gate)}
                              {gate.message ? ` — ${gate.message}` : ''}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                      <p>
                        <Link to="/runs">View runs</Link>
                      </p>
                    </div>
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
