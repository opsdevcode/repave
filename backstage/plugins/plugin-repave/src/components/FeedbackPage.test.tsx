import {
  buildFeedbackRequest,
  FEEDBACK_SURFACE,
  feedbackQueryDefaults,
  parseFeedbackPayload,
  rowsFromFeedbackEvents,
} from './FeedbackPage';

describe('feedback helpers', () => {
  it('maps rollup and event rows', () => {
    const rows = rowsFromFeedbackEvents([
      {
        submitted_at: '2026-08-15T12:00:00Z',
        csat: 4,
        blueprint_name: 'terraform-module-generic',
        friction_tags: ['slow', 'gates-heavy'],
        comment: 'took a while',
        acting_user: 'builder',
      },
      {},
    ]);
    expect(rows).toEqual([
      {
        submittedAt: '2026-08-15T12:00:00Z',
        csat: 4,
        blueprint: 'terraform-module-generic',
        friction: 'slow, gates-heavy',
        comment: 'took a while',
        actingUser: 'builder',
      },
    ]);
    const view = parseFeedbackPayload({
      rollup: { event_count: 2, csat_average: 4.25 },
      events: [{ submitted_at: '2026-08-15T12:00:00Z', csat: 5 }],
    });
    expect(view.eventCount).toBe(2);
    expect(view.csatAverage).toBe('4.3');
    expect(view.events).toHaveLength(1);
  });

  it('reads blueprint and run id from the query string', () => {
    expect(feedbackQueryDefaults('?blueprint=helm-chart-generic&run_id=run-9')).toEqual({
      blueprint: 'helm-chart-generic',
      runId: 'run-9',
    });
  });

  it('requires CSAT 1-5 and a blueprint, then stamps surface=backstage', () => {
    expect(
      buildFeedbackRequest({
        csat: '0',
        blueprint: 'helm-chart-generic',
        blueprintVersion: '',
        comment: '',
        runId: '',
        gatesOutcome: '',
        dryRun: false,
        frictionTags: [],
      }).ok,
    ).toBe(false);
    expect(
      buildFeedbackRequest({
        csat: '4',
        blueprint: '',
        blueprintVersion: '',
        comment: '',
        runId: '',
        gatesOutcome: '',
        dryRun: false,
        frictionTags: [],
      }).ok,
    ).toBe(false);
    expect(
      buildFeedbackRequest({
        csat: '4',
        blueprint: 'helm-chart-generic',
        blueprintVersion: '1.2.0',
        comment: 'smooth',
        runId: 'run-9',
        gatesOutcome: 'passed',
        dryRun: true,
        frictionTags: ['slow', 'not-a-tag'],
      }),
    ).toEqual({
      ok: true,
      body: {
        csat: 4,
        blueprint_name: 'helm-chart-generic',
        surface: FEEDBACK_SURFACE,
        dry_run: true,
        friction_tags: ['slow'],
        blueprint_version: '1.2.0',
        comment: 'smooth',
        run_id: 'run-9',
        gates_outcome: 'passed',
      },
    });
  });
});
