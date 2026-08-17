import { NIGHT_OPS_AMBER, nightOpsTheme } from './nightOps';

describe('nightOpsTheme', () => {
  it('uses amber primary on the Material v4 theme', () => {
    const theme = nightOpsTheme.getTheme('v4') as {
      palette?: { primary?: { main?: string } };
    };
    expect(theme?.palette?.primary?.main).toBe(NIGHT_OPS_AMBER);
  });
});
