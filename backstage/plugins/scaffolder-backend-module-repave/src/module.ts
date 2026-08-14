import { createBackendModule, coreServices } from '@backstage/backend-plugin-api';
import { scaffolderActionsExtensionPoint } from '@backstage/plugin-scaffolder-node';
import { createRepaveGenerateAction } from './actions/generate';

export const scaffolderModuleRepave = createBackendModule({
  pluginId: 'scaffolder',
  moduleId: 'repave',
  register(env) {
    env.registerInit({
      deps: {
        scaffolder: scaffolderActionsExtensionPoint,
        config: coreServices.rootConfig,
      },
      async init({ scaffolder, config }) {
        scaffolder.addActions(createRepaveGenerateAction({ config }));
      },
    });
  },
});
