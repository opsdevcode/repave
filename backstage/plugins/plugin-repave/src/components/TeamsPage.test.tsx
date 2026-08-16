import { averageMaturity, parseApiDetail, parseTeamEntities, teamsPath } from './TeamsPage';

describe('teams helpers', () => {
  it('maps entities and averages maturity levels', () => {
    const rows = parseTeamEntities({
      entities: [
        {
          entity_id: 'github.com/acme/tf-app',
          display_name: 'tf-app',
          owner: 'platform',
          team_slug: 'platform',
          maturity: { level: 2, label: 'L2' },
        },
        {
          entity_id: 'github.com/acme/tf-lib',
          maturity: { level: 4, label: 'L4' },
        },
        { display_name: 'skip' },
      ],
    });
    expect(rows).toHaveLength(2);
    expect(averageMaturity(rows)).toBe('3.0');
    expect(averageMaturity([])).toBe('n/a');
    expect(teamsPath(' platform ')).toBe('/teams?slug=platform');
    expect(parseApiDetail({ detail: 'Entity not found' }, 'fallback')).toBe('Entity not found');
  });
});
