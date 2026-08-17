const DEFAULT_MARK = '/static/brand/svg/repave-mark-dark.svg';

export function portalHomeHref(portalBaseUrl: string): string {
  const base = portalBaseUrl.replace(/\/$/, '');
  return base || '/';
}

export function portalNavHref(portalBaseUrl: string, path: string): string {
  const base = portalHomeHref(portalBaseUrl);
  const suffix = path.startsWith('/') ? path : `/${path}`;
  if (base === '/') {
    return suffix;
  }
  return `${base}${suffix}`;
}

export function portalMarkHref(portalBaseUrl: string, logoUrl?: string): string {
  if (logoUrl) {
    return logoUrl;
  }
  return portalNavHref(portalBaseUrl, DEFAULT_MARK);
}

export const PORTAL_NAV_ITEMS = [
  { label: 'Golden paths', path: '/' },
  { label: 'Library', path: '/library' },
  { label: 'Upgrade', path: '/update' },
  { label: 'Verify', path: '/verify' },
] as const;
