import {
  catalogItemToEntity,
  entityNameFromId,
  RepaveEntityProvider,
} from './provider';

function mockLogger() {
  return {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
  };
}

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

describe('RepaveEntityProvider.refresh', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('stays idle when apiBaseUrl is unset', async () => {
    const applyMutation = jest.fn();
    const provider = new RepaveEntityProvider({
      apiBaseUrl: '',
      token: '',
      logger: mockLogger() as never,
    });
    await provider.connect({ applyMutation } as never);
    expect(applyMutation).toHaveBeenCalledWith({ type: 'full', entities: [] });
  });

  it('does not throw when the engine is unreachable', async () => {
    global.fetch = jest.fn().mockRejectedValue(new TypeError('fetch failed'));
    const applyMutation = jest.fn();
    const provider = new RepaveEntityProvider({
      apiBaseUrl: 'http://repave:8088',
      token: '',
      logger: mockLogger() as never,
    });
    await expect(
      provider.connect({ applyMutation } as never),
    ).resolves.toBeUndefined();
    expect(applyMutation).not.toHaveBeenCalled();
  });

  it('does not throw when the engine returns a non-OK status', async () => {
    global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 503 });
    const applyMutation = jest.fn();
    const provider = new RepaveEntityProvider({
      apiBaseUrl: 'http://repave:8088',
      token: '',
      logger: mockLogger() as never,
    });
    await expect(
      provider.connect({ applyMutation } as never),
    ).resolves.toBeUndefined();
    expect(applyMutation).not.toHaveBeenCalled();
  });
});
