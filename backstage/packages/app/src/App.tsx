import { createApp } from '@backstage/frontend-defaults';
import catalogPlugin from '@backstage/plugin-catalog/alpha';
import scaffolderPlugin from '@backstage/plugin-scaffolder/alpha';
import techdocsPlugin from '@backstage/plugin-techdocs/alpha';
import { chromeModule } from './modules/chrome';
import { navModule } from './modules/nav';
import { repavePlugin } from '@internal/plugin-repave';

export const appFeatures = [
  catalogPlugin,
  scaffolderPlugin,
  techdocsPlugin,
  chromeModule,
  navModule,
  repavePlugin,
];

export default createApp({
  features: appFeatures,
});
