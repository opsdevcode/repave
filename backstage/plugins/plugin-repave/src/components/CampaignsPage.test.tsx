import {
  buildCampaignPausedRequest,
  campaignPausedPath,
  parseCampaignsPayload,
} from './CampaignsPage';

describe('campaigns helpers', () => {
  it('parses campaigns and builds a pause request', () => {
    const view = parseCampaignsPayload({
      operator_status_enabled: true,
      gitops_namespace: 'repave-system',
      snapshot: {
        updated_at: '2026-08-16T12:00:00Z',
        campaigns: [
          {
            name: 'platform-rollout',
            namespace: 'repave-system',
            phase: 'Active',
            paused: false,
            open_pr_count: 1,
            out_of_date_count: 2,
          },
        ],
      },
      remediation_queue: [
        {
          repo_url: 'https://github.com/acme/tf-vpc',
          phase: 'OutOfDate',
          remediation_pr_url: 'https://github.com/acme/tf-vpc/pull/9',
        },
      ],
    });
    expect(view.campaigns[0]?.name).toBe('platform-rollout');
    expect(view.remediation[0]?.pullRequestUrl).toContain('/pull/9');
    expect(campaignPausedPath('repave-system', 'platform-rollout')).toBe(
      '/platform/campaigns/repave-system/platform-rollout/paused',
    );
    expect(buildCampaignPausedRequest(true)).toEqual({ paused: true });
  });
});
