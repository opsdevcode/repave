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
  const [view, setView] = useState<FeedbackView | undefined>();
  const [error, setError] = useState('');

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

  return (
    <Page themeId="tool">
      <Header
        title="Feedback"
        subtitle="CSAT and friction from GET /api/v2/platform/feedback. Submit stays on the HTML portal."
      />
      <Content>
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
