import { Link } from '@backstage/core-components';
import { configApiRef, useApi } from '@backstage/frontend-plugin-api';
import { makeStyles } from '@material-ui/core';
import {
  NIGHT_OPS_AMBER,
  NIGHT_OPS_FONT,
  NIGHT_OPS_NAVY,
} from '../../theme/nightOps';
import { PORTAL_NAV_ITEMS, portalMarkHref, portalNavHref } from './portalNav';

const useStyles = makeStyles({
  bar: {
    display: 'flex',
    alignItems: 'center',
    gap: 20,
    minHeight: 56,
    padding: '0 16px',
    background: NIGHT_OPS_NAVY,
    borderBottom: '1px solid #334155',
    color: '#E2E8F0',
    fontFamily: NIGHT_OPS_FONT,
  },
  brand: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    color: 'inherit',
    textDecoration: 'none',
    flexShrink: 0,
  },
  mark: {
    width: 32,
    height: 32,
  },
  wordmark: {
    fontWeight: 700,
    letterSpacing: '-0.02em',
  },
  edition: {
    color: NIGHT_OPS_AMBER,
    fontSize: 12,
    fontWeight: 700,
    marginLeft: 6,
  },
  nav: {
    display: 'flex',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 16,
  },
  link: {
    color: '#94A3B8',
    textDecoration: 'none',
    fontSize: 14,
    fontWeight: 500,
    '&:hover': {
      color: '#E2E8F0',
    },
  },
  current: {
    color: NIGHT_OPS_AMBER,
  },
});

export function PortalAppBar() {
  const classes = useStyles();
  const config = useApi(configApiRef);
  const portalBase = config.getOptionalString('repave.portalBaseUrl') ?? '/';
  const logoUrl = config.getOptionalString('repave.logoUrl') ?? '';
  const accent = config.getOptionalString('repave.accentColor') || NIGHT_OPS_AMBER;
  const markSrc = portalMarkHref(portalBase, logoUrl);

  return (
    <header className={classes.bar} data-testid="repave-portal-chrome">
      <a className={classes.brand} href={portalNavHref(portalBase, '/')}>
        <img className={classes.mark} src={markSrc} alt="" width={32} height={32} />
        <span>
          <span className={classes.wordmark}>repave</span>
          <span className={classes.edition} style={{ color: accent }}>
            v3
          </span>
        </span>
      </a>
      <nav className={classes.nav} aria-label="Primary">
        {PORTAL_NAV_ITEMS.map(item => (
          <a key={item.path} className={classes.link} href={portalNavHref(portalBase, item.path)}>
            {item.label}
          </a>
        ))}
        <Link to="/" underline="none" className={`${classes.link} ${classes.current}`}>
          Catalog
        </Link>
      </nav>
    </header>
  );
}
