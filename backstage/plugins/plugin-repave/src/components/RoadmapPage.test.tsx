import { formatBaseline, formatRatio, parseRoadmapEvidence } from './RoadmapPage';

describe('roadmap evidence helpers', () => {
  it('maps themes, baselines, and sunset candidates', () => {
    expect(formatBaseline(null)).toBe('n/a');
    expect(formatBaseline(true)).toBe('at/above');
    expect(formatBaseline(false)).toBe('below');
    expect(formatRatio(0.2)).toBe('20%');
    const view = parseRoadmapEvidence({
      captured_at: '2026-08-16T12:00:00Z',
      metrics_enabled: true,
      themes: [
        {
          key: 'v185-adoption',
          title: 'Golden path adoption',
          requesting_team: 'platform',
          evidence_kind: 'fleet_adoption',
          evidence_summary: 'Adoption 40%',
          evidence_detail: '4/10 repos',
          meets_baseline: true,
        },
        {},
      ],
      sunset_candidates: [
        {
          blueprint_name: 'terraform-module-generic',
          plans: 10,
          applies: 2,
          conversion_ratio: 0.2,
          review_by: '2026-11-07',
          reason: 'conversion below sunset threshold',
        },
      ],
    });
    expect(view.capturedAt).toBe('2026-08-16T12:00:00Z');
    expect(view.themes[0]?.baseline).toBe('at/above');
    expect(view.sunset[0]?.conversion).toBe('20%');
    expect(view.sunset[0]?.blueprintName).toBe('terraform-module-generic');
  });
});
