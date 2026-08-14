import { createApp } from '@backstage/frontend-defaults';
import catalogPlugin from '@backstage/plugin-catalog/alpha';
import scaffolderPlugin from '@backstage/plugin-scaffolder/alpha';
import { navModule } from './modules/nav';
import { repavePlugin } from '@internal/plugin-repave';

export default createApp({
  features: [catalogPlugin, scaffolderPlugin, navModule, repavePlugin],
});
