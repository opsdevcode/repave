import { parseFeedbackPayload, rowsFromFeedbackEvents } from './FeedbackPage';

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
});
