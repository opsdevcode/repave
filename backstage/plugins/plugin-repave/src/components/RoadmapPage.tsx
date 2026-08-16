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

export type ThemeEvidenceRow = {
  key: string;
  title: string;
  requestingTeam: string;
  evidenceKind: string;
  evidenceSummary: string;
  evidenceDetail: string;
  baseline: string;
};

export type SunsetCandidateRow = {
  blueprintName: string;
  plans: number;
  applies: number;
  conversion: string;
  reviewBy: string;
  reason: string;
};

export type RoadmapView = {
  capturedAt: string;
  metricsEnabled: boolean;
  themes: ThemeEvidenceRow[];
  sunset: SunsetCandidateRow[];
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

export function formatBaseline(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return 'n/a';
  }
  if (value === true || value === 'true') {
    return 'at/above';
  }
  if (value === false || value === 'false') {
    return 'below';
  }
  return 'n/a';
}

export function parseRoadmapEvidence(body: unknown): RoadmapView {
  const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : {};
  const themes = Array.isArray(record.themes)
    ? record.themes
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const row = item as Record<string, unknown>;
          return {
            key: String(row.key ?? ''),
            title: String(row.title ?? ''),
            requestingTeam: String(row.requesting_team ?? ''),
            evidenceKind: String(row.evidence_kind ?? ''),
            evidenceSummary: String(row.evidence_summary ?? ''),
            evidenceDetail: String(row.evidence_detail ?? ''),
            baseline: formatBaseline(row.meets_baseline),
          };
        })
        .filter(row => row.key || row.title)
    : [];
  const sunset = Array.isArray(record.sunset_candidates)
    ? record.sunset_candidates
        .filter(item => item && typeof item === 'object')
        .map(item => {
          const row = item as Record<string, unknown>;
          return {
            blueprintName: String(row.blueprint_name ?? ''),
            plans: Number(row.plans ?? 0),
            applies: Number(row.applies ?? 0),
            conversion: formatRatio(row.conversion_ratio),
            reviewBy: String(row.review_by ?? ''),
            reason: String(row.reason ?? ''),
          };
        })
        .filter(row => row.blueprintName)
    : [];
  return {
    capturedAt: String(record.captured_at ?? ''),
    metricsEnabled: Boolean(record.metrics_enabled),
    themes,
    sunset,
  };
}

function parseJsonBody(text: string): unknown {
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text };
  }
}

const THEME_COLUMNS: TableColumn<ThemeEvidenceRow>[] = [
  { title: 'Theme', field: 'title' },
  { title: 'Requested by', field: 'requestingTeam' },
  { title: 'Evidence', field: 'evidenceSummary' },
  { title: 'Detail', field: 'evidenceDetail' },
  { title: 'Baseline', field: 'baseline' },
];

const SUNSET_COLUMNS: TableColumn<SunsetCandidateRow>[] = [
  { title: 'Blueprint', field: 'blueprintName' },
  { title: 'Plans', field: 'plans' },
  { title: 'Applies', field: 'applies' },
  { title: 'Conversion', field: 'conversion' },
  { title: 'Review by', field: 'reviewBy' },
  { title: 'Reason', field: 'reason' },
];

export function RoadmapPage() {
  const discoveryApi = useApi(discoveryApiRef);
  const fetchApi = useApi(fetchApiRef);
  const [view, setView] = useState<RoadmapView | undefined>();
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    const base = await discoveryApi.getBaseUrl('proxy');
    const response = await fetchApi.fetch(`${base}/repave/api/v2/platform/roadmap-evidence`);
    const text = await response.text();
    const body = parseJsonBody(text);
    if (!response.ok) {
      throw new Error(
        parseApiDetail(body, `GET /api/v2/platform/roadmap-evidence returned ${response.status}`),
      );
    }
    return parseRoadmapEvidence(body);
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

  return (
    <Page themeId="tool">
      <Header
        title="Roadmap evidence"
        subtitle="Theme adoption and sunset candidates from GET /api/v2/platform/roadmap-evidence."
      />
      <Content>
        {error ? <p>{error}</p> : null}
        {view === undefined && !error ? <Progress /> : null}
        {view ? (
          <>
            <InfoCard title="Snapshot">
              <StructuredMetadataTable
                metadata={{
                  Captured: view.capturedAt || 'n/a',
                  Themes: String(view.themes.length),
                  'Sunset candidates': String(view.sunset.length),
                  Metrics: view.metricsEnabled ? 'On' : 'Off',
                }}
              />
            </InfoCard>
            <Table
              title="Theme adoption evidence"
              options={{ paging: view.themes.length > 10, search: true, padding: 'dense' }}
              columns={THEME_COLUMNS}
              data={view.themes}
              emptyContent={<p>No theme evidence rows.</p>}
            />
            <Table
              title="Sunset / simplification candidates"
              options={{ paging: view.sunset.length > 10, search: true, padding: 'dense' }}
              columns={SUNSET_COLUMNS}
              data={view.sunset}
              emptyContent={<p>No golden paths are below the sunset conversion threshold.</p>}
            />
          </>
        ) : null}
      </Content>
    </Page>
  );
}
