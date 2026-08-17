import { useEntity } from '@backstage/plugin-catalog-react';
import { InfoCard, Link, StructuredMetadataTable } from '@backstage/core-components';
import { configApiRef, useApi } from '@backstage/frontend-plugin-api';

const ANNOTATIONS = [
  ['repave.dev/blueprint', 'Blueprint'],
  ['repave.dev/blueprint-version', 'Blueprint version'],
  ['repave.dev/standard-source', 'Standard'],
  ['repave.dev/standard-version', 'Standard version'],
  ['repave.dev/engine-version', 'Engine version'],
  ['repave.dev/artifact-type', 'Artifact type'],
  ['repave.dev/catalog-domain', 'Domain'],
  ['backstage.io/kubernetes-id', 'Kubernetes id'],
  ['backstage.io/kubernetes-namespace', 'Kubernetes namespace'],
  ['github.com/project-slug', 'GitHub'],
] as const;

export function hasRepaveLineage(annotations: Record<string, string> | undefined): boolean {
  return Boolean(annotations?.['repave.dev/blueprint']);
}

export function portalHomeHref(portalBaseUrl: string): string {
  const base = portalBaseUrl.replace(/\/$/, '');
  return base || '/';
}

function portalPath(portalBaseUrl: string, path: string): string {
  const base = portalHomeHref(portalBaseUrl);
  const suffix = path.startsWith('/') ? path : `/${path}`;
  if (base === '/') {
    return suffix;
  }
  return `${base}${suffix}`;
}

export function portalGenerateHref(portalBaseUrl: string, blueprint: string): string {
  if (!blueprint) {
    return portalHomeHref(portalBaseUrl);
  }
  return portalPath(portalBaseUrl, `/blueprints/${encodeURIComponent(blueprint)}`);
}

export function portalUpgradeHref(portalBaseUrl: string): string {
  return portalPath(portalBaseUrl, '/update');
}

export function githubSourceUrl(annotations: Record<string, string>): string | undefined {
  const slug = annotations['github.com/project-slug'];
  if (slug) {
    return `https://github.com/${slug}`;
  }
  const loc = annotations['backstage.io/source-location'];
  if (loc?.startsWith('url:')) {
    return loc.slice(4);
  }
  return undefined;
}

export function RepaveLineageCard() {
  const { entity } = useEntity();
  const config = useApi(configApiRef);
  const annotations = entity.metadata.annotations ?? {};
  if (!hasRepaveLineage(annotations)) {
    return null;
  }
  const metadata: Record<string, string> = {};
  for (const [key, label] of ANNOTATIONS) {
    const value = annotations[key];
    if (value) {
      metadata[label] = value;
    }
  }
  const portalBase = config.getOptionalString('repave.portalBaseUrl') ?? '/';
  const blueprint = annotations['repave.dev/blueprint'] ?? '';
  const sourceUrl = githubSourceUrl(annotations);
  return (
    <InfoCard title="Repave lineage">
      <StructuredMetadataTable metadata={metadata} />
      <p>
        <Link to={portalGenerateHref(portalBase, blueprint)}>Generate in portal</Link>
        {' · '}
        <Link to={portalUpgradeHref(portalBase)}>Upgrade in portal</Link>
        {sourceUrl ? (
          <>
            {' · '}
            <Link to={sourceUrl} target="_blank" rel="noopener noreferrer">
              View source
            </Link>
          </>
        ) : null}
      </p>
    </InfoCard>
  );
}
