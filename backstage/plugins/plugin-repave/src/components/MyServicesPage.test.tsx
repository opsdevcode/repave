import type { Entity } from '@backstage/catalog-model';
import { rowsFromEntities } from './MyServicesPage';

function component(name: string, annotations?: Record<string, string>): Entity {
  return {
    apiVersion: 'backstage.io/v1alpha1',
    kind: 'Component',
    metadata: {
      name,
      title: name,
      annotations,
    },
    spec: { type: 'service', owner: 'group:platform' },
  };
}

describe('rowsFromEntities', () => {
  it('keeps components with repave lineage and drops the rest', () => {
    const rows = rowsFromEntities([
      component('example-website'),
      component('tf-aws-demo', {
        'repave.dev/blueprint': 'terraform-module-generic',
        'repave.dev/blueprint-version': '1.2.3',
      }),
    ]);
    expect(rows).toEqual([
      {
        name: 'tf-aws-demo',
        namespace: 'default',
        title: 'tf-aws-demo',
        owner: 'group:platform',
        blueprint: 'terraform-module-generic',
        blueprintVersion: '1.2.3',
      },
    ]);
  });
});
