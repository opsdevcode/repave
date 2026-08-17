import { createApp } from '@backstage/frontend-defaults';
import catalogPlugin from '@backstage/plugin-catalog/alpha';
import scaffolderPlugin from '@backstage/plugin-scaffolder/alpha';
import { chromeModule } from './modules/chrome';
import { navModule } from './modules/nav';
import { repavePlugin } from '@internal/plugin-repave';

export default createApp({
  features: [catalogPlugin, scaffolderPlugin, chromeModule, navModule, repavePlugin],
});
