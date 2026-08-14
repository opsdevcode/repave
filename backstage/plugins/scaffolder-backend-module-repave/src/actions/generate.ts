import { Config } from '@backstage/config';
import { createTemplateAction } from '@backstage/plugin-scaffolder-node';

const DEFAULT_TIMEOUT_MS = 30_000;

export function createRepaveGenerateAction(options: { config: Config }) {
  const apiBaseUrl = options.config.getOptionalString('repave.apiBaseUrl') ?? '';
  const token = options.config.getOptionalString('repave.apiToken') ?? '';

  return createTemplateAction({
    id: 'repave:generate',
    description: 'Generate a golden path via POST /api/v2/generate',
    schema: {
      input: {
        blueprint: z =>
          z.string({
            description: 'Blueprint name, for example terraform-module-generic',
          }),
        dryRun: z =>
          z
            .boolean({ description: 'Plan only when true (default)' })
            .optional(),
        inputs: z =>
          z
            .record(z.unknown(), {
              description: 'Blueprint inputs passed to /api/v2/generate',
            })
            .optional(),
      },
      output: {
        summary: z => z.string(),
        gatesOutcome: z => z.string(),
        files: z => z.array(z.string()),
        dryRun: z => z.boolean(),
      },
    },
    async handler(ctx) {
      if (!apiBaseUrl) {
        throw new Error(
          'repave.apiBaseUrl is not set; set it in app-config.yaml or REPAVE_API_BASE_URL',
        );
      }
      const blueprint = String(ctx.input.blueprint ?? '').trim();
      if (!blueprint) {
        throw new Error('blueprint is required');
      }
      const dryRun = ctx.input.dryRun !== false;
      const inputs =
        ctx.input.inputs && typeof ctx.input.inputs === 'object'
          ? (ctx.input.inputs as Record<string, unknown>)
          : {};

      const url = `${apiBaseUrl.replace(/\/$/, '')}/api/v2/generate`;
      ctx.logger.info(`POST ${url} blueprint=${blueprint} dry_run=${dryRun}`);

      const headers: Record<string, string> = {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      };
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          blueprint,
          dry_run: dryRun,
          inputs,
        }),
        signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
      });
      const text = await response.text();
      let body: Record<string, unknown> = {};
      try {
        body = text ? (JSON.parse(text) as Record<string, unknown>) : {};
      } catch {
        body = { detail: text };
      }
      if (!response.ok) {
        const detail = String(body.detail ?? text ?? response.status);
        throw new Error(
          `POST /api/v2/generate returned ${response.status}: ${detail}`,
        );
      }
      const gatesOutcome = String(body.gates_outcome ?? '');
      const summary =
        gatesOutcome ||
        String(body.summary ?? body.message ?? 'generate completed');
      const files = Array.isArray(body.rendered_files)
        ? body.rendered_files.map(item =>
            typeof item === 'object' && item && 'path' in item
              ? String((item as { path: string }).path)
              : String(item),
          )
        : [];
      ctx.output('summary', summary);
      ctx.output('gatesOutcome', gatesOutcome);
      ctx.output('files', files);
      ctx.output('dryRun', dryRun);
    },
  });
}
