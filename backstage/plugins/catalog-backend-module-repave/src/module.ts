import { createBackendModule, coreServices } from '@backstage/backend-plugin-api';
import { catalogProcessingExtensionPoint } from '@backstage/plugin-catalog-node';
import { RepaveEntityProvider } from './provider';

export const catalogModuleRepave = createBackendModule({
  pluginId: 'catalog',
  moduleId: 'repave',
  register(env) {
    env.registerInit({
      deps: {
        catalog: catalogProcessingExtensionPoint,
        config: coreServices.rootConfig,
        logger: coreServices.logger,
        scheduler: coreServices.scheduler,
      },
      async init({ catalog, config, logger, scheduler }) {
        const provider = RepaveEntityProvider.fromConfig(config, { logger, scheduler });
        catalog.addEntityProvider(provider);
        await scheduler.scheduleTask({
          id: 'repave-catalog-refresh',
          frequency: { minutes: 10 },
          timeout: { minutes: 2 },
          fn: async () => provider.refresh(),
        });
      },
    });
  },
});
