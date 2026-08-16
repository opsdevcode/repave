import { formatSeconds, parseValueStreamPayload } from './ValueStreamPage';

describe('value-stream helpers', () => {
  it('parses current ratios and history points', () => {
    const view = parseValueStreamPayload({
      captured_at: '2026-08-15T12:00:00Z',
      adoption_ratio: 0.4,
      plan_apply_ratio: 0.5,
      governed_count: 4,
      eligible_count: 10,
      time_to_first_artifact_seconds_p50: 120,
      history: [
        { captured_at: '2026-08-14T12:00:00Z', adoption_ratio: 0.3, plan_apply_ratio: 0.4 },
      ],
    });
    expect(view.adoptionRatio).toBe('40%');
    expect(view.timeToFirstP50).toBe('120s');
    expect(view.history[0]?.adoptionRatio).toBe('30%');
    expect(formatSeconds(null)).toBe('n/a');
  });
});
