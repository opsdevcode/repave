import {
  buildVendRequest,
  isValidStackName,
  parseSandboxCatalog,
  rowsFromDeploymentSets,
} from './SandboxPage';

describe('sandbox catalog helpers', () => {
  it('maps deployment sets and drops rows without an id', () => {
    const rows = rowsFromDeploymentSets([
      {
        id: 'api-sandbox-7d',
        label: 'API sandbox (7 days)',
        workload_profile: 'api-sandbox',
        class: 'sandbox',
        ttl_hours: 168,
        cloud_provider: 'aws',
        environment: 'dev',
      },
      { label: 'orphan' },
    ]);
    expect(rows).toEqual([
      {
        id: 'api-sandbox-7d',
        label: 'API sandbox (7 days)',
        description: '',
        workloadProfile: 'api-sandbox',
        envClass: 'sandbox',
        ttlHours: 168,
        cloudProvider: 'aws',
        environment: 'dev',
      },
    ]);
  });

  it('parses the /api/v2/deployment-sets payload', () => {
    const catalog = parseSandboxCatalog({
      vend_available: true,
      developer_lab: true,
      default_owner: 'group:platform',
      deployment_sets: [{ id: 'api-sandbox-7d', label: 'API sandbox' }],
    });
    expect(catalog.vendAvailable).toBe(true);
    expect(catalog.developerLab).toBe(true);
    expect(catalog.defaultOwner).toBe('group:platform');
    expect(catalog.rows[0]?.id).toBe('api-sandbox-7d');
  });

  it('validates stack names the same way as the engine', () => {
    expect(isValidStackName('my-feature-sandbox')).toBe(true);
    expect(isValidStackName('Bad_Name')).toBe(false);
    expect(isValidStackName('ab')).toBe(false);
  });

  it('builds a vend body or names the field to change', () => {
    expect(
      buildVendRequest({
        deploymentSet: 'api-sandbox-7d',
        stackName: 'my-feature-sandbox',
        owner: 'group:platform',
        dryRun: true,
      }),
    ).toEqual({
      ok: true,
      body: {
        deployment_set: 'api-sandbox-7d',
        stack_name: 'my-feature-sandbox',
        owner: 'group:platform',
        dry_run: true,
      },
    });
    expect(
      buildVendRequest({
        deploymentSet: '',
        stackName: 'my-feature-sandbox',
        owner: '',
        dryRun: true,
      }).ok,
    ).toBe(false);
  });
});
