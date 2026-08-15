import {
  buildVerifyRequest,
  gateStatusLabel,
  isVerifyResultStatus,
  looksLikeRemoteTarget,
  parseApiDetail,
  parseVerifyResult,
} from './VerifyPage';

describe('verify helpers', () => {
  it('sends repo_url for remotes and path for local checkouts', () => {
    expect(looksLikeRemoteTarget('https://github.com/acme/tf-vpc')).toBe(true);
    expect(looksLikeRemoteTarget('git@github.com:acme/tf-vpc.git')).toBe(true);
    expect(looksLikeRemoteTarget('/repos/tf-vpc')).toBe(false);
    expect(buildVerifyRequest({ target: '', blueprint: '', ref: '', requireRun: false }).ok).toBe(
      false,
    );
    expect(
      buildVerifyRequest({
        target: 'https://github.com/acme/tf-vpc',
        blueprint: 'terraform-module-generic',
        ref: 'main',
        requireRun: true,
      }),
    ).toEqual({
      ok: true,
      body: {
        repo_url: 'https://github.com/acme/tf-vpc',
        blueprint: 'terraform-module-generic',
        ref: 'main',
        require_run: true,
      },
    });
    expect(
      buildVerifyRequest({
        target: '/repos/tf-vpc',
        blueprint: '',
        ref: '',
        requireRun: false,
      }),
    ).toEqual({
      ok: true,
      body: { path: '/repos/tf-vpc', require_run: false },
    });
  });

  it('parses a verify payload including 422-style failures', () => {
    const result = parseVerifyResult({
      target: '/repos/tf-vpc',
      catalog_blueprint_name: 'terraform-module-generic',
      catalog_blueprint_version: '0.9.0',
      ok: false,
      gates_passed: false,
      pins_aligned: false,
      provenance_present: true,
      remote: false,
      gates: [{ name: 'ruff', passed: false, skipped: false, message: 'lint failed' }],
      pin_changes: [{ field: 'blueprint_version', before: '0.8.0', after: '0.9.0' }],
      components: [
        {
          component_id: 'policy',
          catalog_blueprint_name: 'opa-policy-generic',
          ok: true,
          gates_passed: true,
          pins_aligned: true,
        },
      ],
    });
    expect(result.ok).toBe(false);
    expect(result.gates[0]?.name).toBe('ruff');
    expect(gateStatusLabel(result.gates[0]!)).toBe('failed');
    expect(result.pinChanges[0]?.field).toBe('blueprint_version');
    expect(result.components[0]?.componentId).toBe('policy');
    expect(isVerifyResultStatus(200)).toBe(true);
    expect(isVerifyResultStatus(422)).toBe(true);
    expect(isVerifyResultStatus(400)).toBe(false);
    expect(parseApiDetail({ detail: 'path or repo_url is required' }, 'fallback')).toBe(
      'path or repo_url is required',
    );
  });
});
