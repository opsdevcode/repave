import { createApp } from '@backstage/frontend-defaults';
import apiDocsPlugin from '@backstage/plugin-api-docs/alpha';
import catalogPlugin from '@backstage/plugin-catalog/alpha';
import catalogGraphPlugin from '@backstage/plugin-catalog-graph/alpha';
import catalogImportPlugin from '@backstage/plugin-catalog-import/alpha';
import kubernetesPlugin from '@backstage/plugin-kubernetes/alpha';
import orgPlugin from '@backstage/plugin-org/alpha';
import scaffolderPlugin from '@backstage/plugin-scaffolder/alpha';
import searchPlugin from '@backstage/plugin-search/alpha';
import techdocsPlugin from '@backstage/plugin-techdocs/alpha';
import techdocsAddons, {
  techDocsReportIssueAddonModule,
} from '@backstage/plugin-techdocs-module-addons-contrib/alpha';
import { chromeModule } from './modules/chrome';
import { navModule } from './modules/nav';
import { repavePlugin } from '@internal/plugin-repave';

export const appFeatures = [
  catalogPlugin,
  catalogGraphPlugin,
  catalogImportPlugin,
  apiDocsPlugin,
  searchPlugin,
  orgPlugin,
  kubernetesPlugin,
  scaffolderPlugin,
  techdocsPlugin,
  techdocsAddons,
  techDocsReportIssueAddonModule,
  chromeModule,
  navModule,
  repavePlugin,
];

export default createApp({
  features: appFeatures,
});
