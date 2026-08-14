import { catalogItemToEntity, entityNameFromId } from './provider';

describe('catalogItemToEntity', () => {
  it('maps /api/v2/catalog/entities fields onto repave.dev annotations', () => {
    const entity = catalogItemToEntity({
      entity_id: 'tf-aws-demo',
      display_name: 'tf-aws-demo',
      owner: 'group:platform',
      blueprint_name: 'terraform-module-generic',
      blueprint_version: '1.2.3',
      standard_source: 'standards/terraform',
      standard_version: '4.0.0',
      engine_version: '3.6.0',
      component_type: 'library',
      lifecycle: 'production',
    });
    expect(entity.metadata.name).toBe('tf-aws-demo');
    expect(entity.metadata.annotations?.['repave.dev/blueprint']).toBe(
      'terraform-module-generic',
    );
    expect(entity.metadata.annotations?.['repave.dev/blueprint-version']).toBe('1.2.3');
    expect(entity.metadata.annotations?.['repave.dev/engine-version']).toBe('3.6.0');
    expect(entity.spec).toMatchObject({
      type: 'library',
      owner: 'group:platform',
    });
  });

  it('slugifies entity ids for metadata.name', () => {
    expect(entityNameFromId('Org/TF Module')).toBe('org-tf-module');
  });
});
