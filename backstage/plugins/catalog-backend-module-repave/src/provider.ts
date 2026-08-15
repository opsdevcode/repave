import type { Entity } from '@backstage/catalog-model';
import type { Config } from '@backstage/config';
import type {
  EntityProvider,
  EntityProviderConnection,
} from '@backstage/plugin-catalog-node';
import type { LoggerService, SchedulerService } from '@backstage/backend-plugin-api';

const DEFAULT_TIMEOUT_MS = 15_000;

export function entityNameFromId(entityId: string): string {
  const slug = entityId
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return slug || 'unnamed';
}

export function catalogItemToEntity(item: Record<string, unknown>): Entity {
  const entityId = String(item.entity_id ?? item.display_name ?? 'unnamed');
  const name = entityNameFromId(entityId);
  const owner = String(item.owner ?? 'group:default/platform');
  return {
    apiVersion: 'backstage.io/v1alpha1',
    kind: 'Component',
    metadata: {
      name,
      title: String(item.display_name ?? entityId),
      annotations: {
        'backstage.io/managed-by-location': `url:repave-api/${name}`,
        'backstage.io/managed-by-origin-location': `url:repave-api/${name}`,
        'repave.dev/blueprint': String(item.blueprint_name ?? ''),
        'repave.dev/blueprint-version': String(item.blueprint_version ?? ''),
        'repave.dev/standard-source': String(item.standard_source ?? ''),
        'repave.dev/standard-version': String(item.standard_version ?? ''),
        'repave.dev/engine-version': String(item.engine_version ?? ''),
        'repave.dev/artifact-type': String(item.component_type ?? ''),
        'repave.dev/entity-id': entityId,
      },
    },
    spec: {
      type: String(item.component_type ?? 'service'),
      lifecycle: String(item.lifecycle ?? 'production'),
      owner,
    },
  };
}

export class RepaveEntityProvider implements EntityProvider {
  private connection?: EntityProviderConnection;

  constructor(
    private readonly options: {
      apiBaseUrl: string;
      token: string;
      logger: LoggerService;
    },
  ) {}

  static fromConfig(
    config: Config,
    deps: { logger: LoggerService; scheduler?: SchedulerService },
  ): RepaveEntityProvider {
    return new RepaveEntityProvider({
      apiBaseUrl: config.getOptionalString('repave.apiBaseUrl') ?? '',
      token: config.getOptionalString('repave.apiToken') ?? '',
      logger: deps.logger,
    });
  }

  getProviderName(): string {
    return 'repave-api';
  }

  async connect(connection: EntityProviderConnection): Promise<void> {
    this.connection = connection;
    await this.refresh();
  }

  async refresh(): Promise<void> {
    if (!this.connection) {
      return;
    }
    if (!this.options.apiBaseUrl) {
      this.options.logger.info(
        'repave.apiBaseUrl is unset; catalog provider is idle (file locations still apply)',
      );
      await this.connection.applyMutation({ type: 'full', entities: [] });
      return;
    }
    const url = `${this.options.apiBaseUrl.replace(/\/$/, '')}/api/v2/catalog/entities`;
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (this.options.token) {
      headers.Authorization = `Bearer ${this.options.token}`;
    }
    try {
      const response = await fetch(url, {
        headers,
        signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
      });
      if (!response.ok) {
        this.options.logger.warn(
          `GET /api/v2/catalog/entities returned ${response.status}; retry on the next refresh`,
        );
        return;
      }
      const payload = (await response.json()) as { entities?: unknown[] };
      const items = Array.isArray(payload.entities) ? payload.entities : [];
      const entities = items
        .filter(item => item && typeof item === 'object')
        .map(item => ({
          entity: catalogItemToEntity(item as Record<string, unknown>),
          locationKey: `repave-api:${entityNameFromId(
            String((item as { entity_id?: string }).entity_id ?? ''),
          )}`,
        }));
      await this.connection.applyMutation({ type: 'full', entities });
      this.options.logger.info(`ingested ${entities.length} entities from ${url}`);
    } catch (err) {
      // Engine may still be starting (chart-smoke). Keep last mutation; retry later.
      this.options.logger.warn(
        `catalog refresh skipped: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  }
}
