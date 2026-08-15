import {
  buildRegisterRequest,
  fleetUnregisterPath,
  looksLikeGitRepoUrl,
  parseApiDetail,
  parseFleetPayload,
  rowsFromRepos,
} from './FleetPage';

describe('fleet helpers', () => {
  it('maps list payloads and drops rows without a repo URL', () => {
    const rows = rowsFromRepos([
      {
        repo_url: 'https://github.com/acme/tf-vpc.git',
        display_name: 'tf-vpc',
        family: 'terraform',
        blueprint_name: 'terraform-module-generic',
        blueprint_version: '0.9.0',
        owner: 'group:platform',
        operator_phase: 'Ready',
        operator_message: 'synced',
        remediation_pr_url: 'https://github.com/acme/tf-vpc/pull/12',
      },
      { display_name: 'orphan' },
    ]);
    expect(rows).toEqual([
      {
        repoUrl: 'https://github.com/acme/tf-vpc.git',
        displayName: 'tf-vpc',
        family: 'terraform',
        blueprintName: 'terraform-module-generic',
        blueprintVersion: '0.9.0',
        owner: 'group:platform',
        operatorPhase: 'Ready',
        operatorMessage: 'synced',
        remediationPrUrl: 'https://github.com/acme/tf-vpc/pull/12',
      },
    ]);
  });

  it('parses the /api/v2/fleet payload', () => {
    const payload = parseFleetPayload({
      count: 1,
      repos: [{ repo_url: 'https://github.com/acme/tf-vpc', display_name: 'tf-vpc' }],
    });
    expect(payload.count).toBe(1);
    expect(payload.rows[0]?.displayName).toBe('tf-vpc');
  });

  it('accepts https and git SSH repo URLs', () => {
    expect(looksLikeGitRepoUrl('https://github.com/acme/tf-vpc')).toBe(true);
    expect(looksLikeGitRepoUrl('git@github.com:acme/tf-vpc.git')).toBe(true);
    expect(looksLikeGitRepoUrl('acme/tf-vpc')).toBe(false);
  });

  it('builds a register body or names the field to change', () => {
    expect(
      buildRegisterRequest({
        repoUrl: 'https://github.com/acme/tf-vpc',
        blueprintName: 'terraform-module-generic',
        blueprintVersion: '0.9.0',
        owner: 'group:platform',
      }),
    ).toEqual({
      ok: true,
      body: {
        repo_url: 'https://github.com/acme/tf-vpc',
        blueprint_name: 'terraform-module-generic',
        blueprint_version: '0.9.0',
        owner: 'group:platform',
      },
    });
    expect(
      buildRegisterRequest({
        repoUrl: '',
        blueprintName: 'terraform-module-generic',
        blueprintVersion: '',
        owner: '',
      }).ok,
    ).toBe(false);
    expect(
      buildRegisterRequest({
        repoUrl: 'https://github.com/acme/tf-vpc',
        blueprintName: '',
        blueprintVersion: '',
        owner: '',
      }).ok,
    ).toBe(false);
  });

  it('encodes the unregister query and surfaces API detail', () => {
    expect(fleetUnregisterPath('https://github.com/acme/tf-vpc.git')).toBe(
      '/repave/api/v2/fleet?repo_url=https%3A%2F%2Fgithub.com%2Facme%2Ftf-vpc.git',
    );
    expect(
      parseApiDetail(
        { detail: 'Fleet registry is not configured (set fleet.file or REPAVE_FLEET_FILE)' },
        'fallback',
      ),
    ).toBe('Fleet registry is not configured (set fleet.file or REPAVE_FLEET_FILE)');
    expect(parseApiDetail({}, 'GET /api/v2/fleet returned 404')).toBe(
      'GET /api/v2/fleet returned 404',
    );
  });
});
