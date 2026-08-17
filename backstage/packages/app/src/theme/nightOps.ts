import {
  createBaseThemeOptions,
  createUnifiedTheme,
  genPageTheme,
  palettes,
  shapes,
} from '@backstage/theme';

/** Night-ops tokens from docs/portal-design.md — same mark, navy, amber. */
export const NIGHT_OPS_NAVY = '#0F172A';
export const NIGHT_OPS_SURFACE = '#151c2c';
export const NIGHT_OPS_AMBER = '#F59E0B';
export const NIGHT_OPS_FONT = 'Inter, system-ui, sans-serif';

const page = genPageTheme({
  colors: [NIGHT_OPS_NAVY, NIGHT_OPS_AMBER],
  shape: shapes.wave,
});

export const nightOpsTheme = createUnifiedTheme({
  ...createBaseThemeOptions({
    palette: {
      ...palettes.dark,
      background: {
        default: NIGHT_OPS_NAVY,
        paper: NIGHT_OPS_SURFACE,
      },
      primary: {
        main: NIGHT_OPS_AMBER,
        dark: '#D97706',
      },
      secondary: {
        main: '#94A3B8',
      },
      navigation: {
        ...palettes.dark.navigation,
        background: NIGHT_OPS_NAVY,
        indicator: NIGHT_OPS_AMBER,
        color: '#94A3B8',
        selectedColor: '#F1F5F9',
      },
    },
  }),
  fontFamily: NIGHT_OPS_FONT,
  defaultPageTheme: 'home',
  pageTheme: {
    home: page,
    documentation: page,
    tool: genPageTheme({
      colors: [NIGHT_OPS_NAVY, NIGHT_OPS_AMBER],
      shape: shapes.round,
    }),
    service: page,
    website: page,
    library: page,
    other: page,
    app: page,
    apis: page,
  },
});
