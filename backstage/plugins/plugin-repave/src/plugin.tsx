import { createFrontendPlugin, PageBlueprint } from '@backstage/frontend-plugin-api';
import { EntityCardBlueprint } from '@backstage/plugin-catalog-react/alpha';
import AppsIcon from '@material-ui/icons/Apps';
import DeveloperBoardIcon from '@material-ui/icons/DeveloperBoard';
import HistoryIcon from '@material-ui/icons/History';
import { MyServicesPage } from './components/MyServicesPage';
import { RepaveLineageCard } from './components/RepaveLineageCard';
import { RunsPage } from './components/RunsPage';
import { SandboxPage } from './components/SandboxPage';

const myServicesPage = PageBlueprint.make({
  name: 'my-services',
  params: {
    path: '/my-services',
    title: 'My services',
    icon: <AppsIcon />,
    loader: async () => <MyServicesPage />,
  },
});

const sandboxPage = PageBlueprint.make({
  name: 'sandbox',
  params: {
    path: '/sandbox',
    title: 'Sandbox',
    icon: <DeveloperBoardIcon />,
    loader: async () => <SandboxPage />,
  },
});

const runsPage = PageBlueprint.make({
  name: 'runs',
  params: {
    path: '/runs',
    title: 'Runs',
    icon: <HistoryIcon />,
    loader: async () => <RunsPage />,
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
  extensions: [myServicesPage, sandboxPage, runsPage, repaveLineageCard],
});
