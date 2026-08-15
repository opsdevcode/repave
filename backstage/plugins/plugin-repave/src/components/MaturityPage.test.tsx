import {
  formatRatio,
  parseInitiativesPayload,
  parseMaturityPayload,
  rowsFromInitiatives,
} from './MaturityPage';

describe('maturity helpers', () => {
  it('parses maturity distribution and bottom entities', () => {
    const view = parseMaturityPayload({
      catalog_enabled: true,
      entity_count: 3,
      average_level: 2.5,
      by_level: [
        { level: 1, count: 1 },
        { level: 3, count: 2 },
      ],
      bottom_entities: [
        {
          entity_id: 'tf-vpc',
          display_name: 'tf-vpc',
          owner: 'group:platform',
          maturity_level: 1,
          maturity_label: 'Adopting',
        },
      ],
    });
    expect(view.averageLevel).toBe('2.5');
    expect(view.byLevel).toEqual([
      { level: 1, count: 1 },
      { level: 3, count: 2 },
    ]);
    expect(view.bottom[0]?.entityId).toBe('tf-vpc');
  });

  it('maps initiative progress rows', () => {
    const rows = rowsFromInitiatives([
      {
        initiative: {
          id: 'init-1',
          title: 'Runbook coverage',
          owning_team: 'platform',
          target_level: 3,
        },
        passed: 2,
        total: 4,
        ratio: 0.5,
        overdue: true,
      },
      { passed: 1 },
    ]);
    expect(rows).toEqual([
      {
        id: 'init-1',
        title: 'Runbook coverage',
        owningTeam: 'platform',
        targetLevel: 3,
        passed: 2,
        total: 4,
        ratio: '50%',
        overdue: true,
      },
    ]);
    expect(
      parseInitiativesPayload({
        initiatives: [{ initiative: { id: 'init-2', title: 'Tags' }, ratio: 1 }],
      })[0]?.title,
    ).toBe('Tags');
    expect(formatRatio(0.25)).toBe('25%');
  });
});
