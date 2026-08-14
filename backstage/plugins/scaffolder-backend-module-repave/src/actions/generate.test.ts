import { ConfigReader } from '@backstage/config';
import { createRepaveGenerateAction } from './generate';

describe('createRepaveGenerateAction', () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('names the config key when apiBaseUrl is missing', async () => {
    const action = createRepaveGenerateAction({
      config: new ConfigReader({}),
    });
    await expect(
      action.handler({
        input: { blueprint: 'terraform-module-generic' },
        logger: { info: jest.fn() },
        output: jest.fn(),
      } as never),
    ).rejects.toThrow('repave.apiBaseUrl');
  });

  it('posts dry-run generate to /api/v2/generate', async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      text: async () =>
        JSON.stringify({
          blueprint: 'terraform-module-generic',
          gates_outcome: 'passed',
          rendered_files: [{ path: 'main.tf' }],
        }),
    });
    global.fetch = fetchMock as typeof fetch;

    const outputs: Record<string, unknown> = {};
    const action = createRepaveGenerateAction({
      config: new ConfigReader({
        repave: { apiBaseUrl: 'http://engine:8088', apiToken: 'tok' },
      }),
    });
    await action.handler({
      input: {
        blueprint: 'terraform-module-generic',
        dryRun: true,
        inputs: { module_name: 'demo', include_backstage_catalog: 'true' },
      },
      logger: { info: jest.fn() },
      output: (key: string, value: unknown) => {
        outputs[key] = value;
      },
    } as never);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://engine:8088/api/v2/generate');
    expect(init.method).toBe('POST');
    expect(init.headers.Authorization).toBe('Bearer tok');
    expect(JSON.parse(init.body)).toEqual({
      blueprint: 'terraform-module-generic',
      dry_run: true,
      inputs: { module_name: 'demo', include_backstage_catalog: 'true' },
    });
    expect(outputs.summary).toBe('passed');
    expect(outputs.gatesOutcome).toBe('passed');
    expect(outputs.files).toEqual(['main.tf']);
  });
});
