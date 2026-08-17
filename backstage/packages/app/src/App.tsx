import { createApp } from '@backstage/frontend-defaults';
import apiDocsPlugin from '@backstage/plugin-api-docs/alpha';
import catalogPlugin from '@backstage/plugin-catalog/alpha';
import catalogGraphPlugin from '@backstage/plugin-catalog-graph/alpha';
import catalogImportPlugin from '@backstage/plugin-catalog-import/alpha';
import scaffolderPlugin from '@backstage/plugin-scaffolder/alpha';
import searchPlugin from '@backstage/plugin-search/alpha';
import techdocsPlugin from '@backstage/plugin-techdocs/alpha';
import { chromeModule } from './modules/chrome';
import { navModule } from './modules/nav';
import { repavePlugin } from '@internal/plugin-repave';

export const appFeatures = [
  catalogPlugin,
  catalogGraphPlugin,
  catalogImportPlugin,
  apiDocsPlugin,
  searchPlugin,
  scaffolderPlugin,
  techdocsPlugin,
  chromeModule,
  navModule,
  repavePlugin,
];

export default createApp({
  features: appFeatures,
});
