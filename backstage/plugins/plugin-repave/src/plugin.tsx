import { createFrontendPlugin, PageBlueprint } from '@backstage/frontend-plugin-api';
import { EntityCardBlueprint } from '@backstage/plugin-catalog-react/alpha';
import AppsIcon from '@material-ui/icons/Apps';
import AssignmentTurnedInIcon from '@material-ui/icons/AssignmentTurnedIn';
import CloudDownloadIcon from '@material-ui/icons/CloudDownload';
import DeveloperBoardIcon from '@material-ui/icons/DeveloperBoard';
import HistoryIcon from '@material-ui/icons/History';
import MapIcon from '@material-ui/icons/Map';
import StorageIcon from '@material-ui/icons/Storage';
import SystemUpdateAltIcon from '@material-ui/icons/SystemUpdateAlt';
import { EstatePage } from './components/EstatePage';
import { FleetPage } from './components/FleetPage';
import { ImportPage } from './components/ImportPage';
import { MyServicesPage } from './components/MyServicesPage';
import { RepaveLineageCard } from './components/RepaveLineageCard';
import { RunsPage } from './components/RunsPage';
import { SandboxPage } from './components/SandboxPage';
import { UpgradePage } from './components/UpgradePage';
import { VerifyPage } from './components/VerifyPage';

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

const upgradePage = PageBlueprint.make({
  name: 'upgrade',
  params: {
    path: '/upgrade',
    title: 'Upgrade',
    icon: <SystemUpdateAltIcon />,
    loader: async () => <UpgradePage />,
  },
});

const fleetPage = PageBlueprint.make({
  name: 'fleet',
  params: {
    path: '/fleet',
    title: 'Fleet',
    icon: <StorageIcon />,
    loader: async () => <FleetPage />,
  },
});

const importPage = PageBlueprint.make({
  name: 'import',
  params: {
    path: '/import',
    title: 'Import',
    icon: <CloudDownloadIcon />,
    loader: async () => <ImportPage />,
  },
});

const verifyPage = PageBlueprint.make({
  name: 'verify',
  params: {
    path: '/verify',
    title: 'Verify',
    icon: <AssignmentTurnedInIcon />,
    loader: async () => <VerifyPage />,
  },
});

const estatePage = PageBlueprint.make({
  name: 'estate',
  params: {
    path: '/estate',
    title: 'Estate',
    icon: <MapIcon />,
    loader: async () => <EstatePage />,
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
  extensions: [
    myServicesPage,
    sandboxPage,
    runsPage,
    upgradePage,
    fleetPage,
    importPage,
    verifyPage,
    estatePage,
    repaveLineageCard,
  ],
});
