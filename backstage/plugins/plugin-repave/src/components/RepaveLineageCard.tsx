import { useEntity } from '@backstage/plugin-catalog-react';
import { InfoCard, StructuredMetadataTable } from '@backstage/core-components';

const ANNOTATIONS = [
  ['repave.dev/blueprint', 'Blueprint'],
  ['repave.dev/blueprint-version', 'Blueprint version'],
  ['repave.dev/standard-source', 'Standard'],
  ['repave.dev/standard-version', 'Standard version'],
  ['repave.dev/engine-version', 'Engine version'],
  ['repave.dev/artifact-type', 'Artifact type'],
] as const;

export function hasRepaveLineage(annotations: Record<string, string> | undefined): boolean {
  return Boolean(annotations?.['repave.dev/blueprint']);
}

export function RepaveLineageCard() {
  const { entity } = useEntity();
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
  return (
    <InfoCard title="Repave lineage">
      <StructuredMetadataTable metadata={metadata} />
    </InfoCard>
  );
}
