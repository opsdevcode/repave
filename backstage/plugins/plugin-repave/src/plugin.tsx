import { createFrontendPlugin } from '@backstage/frontend-plugin-api';
import { EntityCardBlueprint } from '@backstage/plugin-catalog-react/alpha';
import { RepaveLineageCard } from './components/RepaveLineageCard';

const repaveLineageCard = EntityCardBlueprint.make({
  name: 'lineage',
  params: {
    filter: 'kind:component',
    loader: async () => <RepaveLineageCard />,
  },
});

export const repavePlugin = createFrontendPlugin({
  pluginId: 'repave',
  extensions: [repaveLineageCard],
});
