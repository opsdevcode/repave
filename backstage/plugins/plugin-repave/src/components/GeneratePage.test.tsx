import {
  applyGuidedIdentity,
  buildGenerateRequest,
  parseApiDetail,
  parseBlueprintCatalog,
  parseGenerateResult,
  renderGuidedFrom,
  scaffolderHref,
  slugifyIdentity,
  visibleInputs,
} from './GeneratePage';

describe('generate helpers', () => {
  const moduleInputs = [
    {
      name: 'module_name',
      type: 'string',
      required: true,
      description: 'Name',
      defaultValue: '',
      enumValues: [],
      multi: false,
      advanced: false,
      guidedFrom: '{provider_services}',
    },
    {
      name: 'description',
      type: 'string',
      required: true,
      description: 'What it does',
      defaultValue: '',
      enumValues: [],
      multi: false,
      advanced: false,
      guidedFrom: '{cloud_provider} Terraform module covering {provider_services}.',
    },
    {
      name: 'cloud_provider',
      type: 'string',
      required: true,
      description: 'Cloud',
      defaultValue: 'aws',
      enumValues: ['aws', 'azure', 'gcp'],
      multi: false,
      advanced: false,
      guidedFrom: '',
    },
    {
      name: 'provider_services',
      type: 'string',
      required: true,
      description: 'Services',
      defaultValue: '',
      enumValues: [],
      multi: false,
      advanced: false,
      guidedFrom: '',
    },
    {
      name: 'cost_center',
      type: 'string',
      required: false,
      description: 'Chargeback',
      defaultValue: '',
      enumValues: [],
      multi: false,
      advanced: true,
      guidedFrom: '',
    },
  ];

  it('groups catalog blueprints and parses input schemas', () => {
    const catalog = parseBlueprintCatalog({
      count: 2,
      groups: [
        {
          family: 'terraform',
          title: 'Terraform',
          subtitle: 'Modules',
          blueprints: [
            {
              name: 'terraform-module-generic',
              version: '1.0.0',
              artifact_type: 'terraform-module',
              description: 'Generic module',
              inputs: [
                {
                  name: 'cloud_provider',
                  type: 'string',
                  required: true,
                  default: 'aws',
                  enum: ['aws', 'azure'],
                },
                { name: '' },
              ],
            },
            { name: '' },
          ],
        },
        { family: '', title: 'skip' },
      ],
    });
    expect(catalog.families).toEqual([
      { family: 'terraform', title: 'Terraform', subtitle: 'Modules', count: 1 },
    ]);
    expect(catalog.rows[0]?.name).toBe('terraform-module-generic');
    expect(catalog.rows[0]?.inputs[0]).toEqual({
      name: 'cloud_provider',
      type: 'string',
      required: true,
      description: '',
      defaultValue: 'aws',
      enumValues: ['aws', 'azure'],
      multi: false,
      advanced: false,
      guidedFrom: '',
    });
    expect(scaffolderHref()).toBe('/create');
    expect(parseApiDetail({ detail: 'missing catalog' }, 'fallback')).toBe('missing catalog');
  });

  it('hides guided and advanced inputs until asked', () => {
    expect(visibleInputs(moduleInputs, false).map(field => field.name)).toEqual([
      'cloud_provider',
      'provider_services',
    ]);
    expect(visibleInputs(moduleInputs, true).map(field => field.name)).toEqual([
      'cloud_provider',
      'provider_services',
      'cost_center',
    ]);
  });

  it('fills guided identity from selections', () => {
    expect(slugifyIdentity('S3, EC2')).toBe('s3-ec2');
    expect(
      renderGuidedFrom('{cloud_provider} Terraform module covering {provider_services}.', {
        cloud_provider: 'aws',
        provider_services: 's3',
      }, { slug: false, separator: '-' }),
    ).toBe('aws Terraform module covering s3.');
    const filled = applyGuidedIdentity(moduleInputs, {
      cloud_provider: 'aws',
      provider_services: 's3',
      module_name: '',
      description: '',
      cost_center: '',
    });
    expect(filled.module_name).toBe('s3');
    expect(filled.description).toBe('aws Terraform module covering s3.');
  });

  it('builds a dry-run generate body or names the field to change', () => {
    expect(
      buildGenerateRequest({
        blueprint: 'terraform-module-generic',
        values: {
          cloud_provider: 'aws',
          provider_services: 's3',
          module_name: '',
          description: '',
          cost_center: '',
        },
        inputs: moduleInputs,
        dryRun: true,
      }),
    ).toEqual({
      ok: true,
      body: {
        blueprint: 'terraform-module-generic',
        dry_run: true,
        inputs: {
          cloud_provider: 'aws',
          provider_services: 's3',
          module_name: 's3',
          description: 'aws Terraform module covering s3.',
        },
      },
    });
    expect(
      buildGenerateRequest({
        blueprint: '',
        values: {},
        inputs: moduleInputs,
        dryRun: true,
      }),
    ).toEqual({ ok: false, error: 'Pick a blueprint' });
    expect(
      buildGenerateRequest({
        blueprint: 'terraform-module-generic',
        values: { cloud_provider: 'aws', provider_services: '' },
        inputs: moduleInputs,
        dryRun: true,
      }),
    ).toEqual({
      ok: false,
      error: 'Set provider_services so module_name can be filled',
    });
  });

  it('parses a generate result including file count', () => {
    expect(
      parseGenerateResult({
        blueprint: 'terraform-module-generic',
        gates_outcome: 'passed',
        gates_passed: true,
        rendered_files: 4,
        gates: [
          { name: 'terraform-fmt', passed: true, skipped: false, message: '' },
          { name: '' },
        ],
      }),
    ).toEqual({
      blueprint: 'terraform-module-generic',
      gatesOutcome: 'passed',
      gatesPassed: true,
      fileCount: 4,
      gates: [{ name: 'terraform-fmt', passed: true, skipped: false, message: '' }],
    });
  });
});
