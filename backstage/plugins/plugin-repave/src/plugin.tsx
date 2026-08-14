import { createFrontendPlugin, PageBlueprint } from '@backstage/frontend-plugin-api';
import { EntityCardBlueprint } from '@backstage/plugin-catalog-react/alpha';
import AppsIcon from '@material-ui/icons/Apps';
import { MyServicesPage } from './components/MyServicesPage';
import { RepaveLineageCard } from './components/RepaveLineageCard';

const myServicesPage = PageBlueprint.make({
  name: 'my-services',
  params: {
    path: '/my-services',
    title: 'My services',
    icon: <AppsIcon />,
    loader: async () => <MyServicesPage />,
  },
});

const repaveLineageCard = EntityCardBlueprint.make({
  name: 'lineage',
  params: {
    filter: 'kind:component',
    loader: async () => <RepaveLineageCard />,
  },
});

export const repavePlugin = createFrontendPlugin({
  pluginId: 'repave',
  extensions: [myServicesPage, repaveLineageCard],
});
