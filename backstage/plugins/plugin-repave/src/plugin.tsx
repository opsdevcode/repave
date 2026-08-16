import { createFrontendPlugin, PageBlueprint } from '@backstage/frontend-plugin-api';
import { EntityCardBlueprint } from '@backstage/plugin-catalog-react/alpha';
import AccountBalanceIcon from '@material-ui/icons/AccountBalance';
import AppsIcon from '@material-ui/icons/Apps';
import AssessmentIcon from '@material-ui/icons/Assessment';
import AssignmentTurnedInIcon from '@material-ui/icons/AssignmentTurnedIn';
import BarChartIcon from '@material-ui/icons/BarChart';
import BuildIcon from '@material-ui/icons/Build';
import CategoryIcon from '@material-ui/icons/Category';
import CloudDownloadIcon from '@material-ui/icons/CloudDownload';
import DeveloperBoardIcon from '@material-ui/icons/DeveloperBoard';
import FeedbackIcon from '@material-ui/icons/Feedback';
import FlagIcon from '@material-ui/icons/Flag';
import HistoryIcon from '@material-ui/icons/History';
import LibraryAddIcon from '@material-ui/icons/LibraryAdd';
import MapIcon from '@material-ui/icons/Map';
import MenuBookIcon from '@material-ui/icons/MenuBook';
import NewReleasesIcon from '@material-ui/icons/NewReleases';
import PlaylistAddIcon from '@material-ui/icons/PlaylistAdd';
import RestoreIcon from '@material-ui/icons/Restore';
import SecurityIcon from '@material-ui/icons/Security';
import ShowChartIcon from '@material-ui/icons/ShowChart';
import StorageIcon from '@material-ui/icons/Storage';
import SystemUpdateAltIcon from '@material-ui/icons/SystemUpdateAlt';
import TimelineIcon from '@material-ui/icons/Timeline';
import { ActivityPage } from './components/ActivityPage';
import { AddComponentPage } from './components/AddComponentPage';
import { CampaignsPage } from './components/CampaignsPage';
import { CompliancePage } from './components/CompliancePage';
import { EstatePage } from './components/EstatePage';
import { FeedbackPage } from './components/FeedbackPage';
import { FinOpsPage } from './components/FinOpsPage';
import { FleetPage } from './components/FleetPage';
import { ImportBatchPage } from './components/ImportBatchPage';
import { ImportPage } from './components/ImportPage';
import { MaturityPage } from './components/MaturityPage';
import { MetricsPage } from './components/MetricsPage';
import { MyServicesPage } from './components/MyServicesPage';
import { OpsPage } from './components/OpsPage';
import { ReclaimPage } from './components/ReclaimPage';
import { RepaveLineageCard } from './components/RepaveLineageCard';
import { RoadmapPage } from './components/RoadmapPage';
import { RunsPage } from './components/RunsPage';
import { SandboxPage } from './components/SandboxPage';
import { StandardsPage } from './components/StandardsPage';
import { UpgradePage } from './components/UpgradePage';
import { ValueStreamPage } from './components/ValueStreamPage';
import { VendComponentPage } from './components/VendComponentPage';
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

const vendComponentPage = PageBlueprint.make({
  name: 'vend',
  params: {
    path: '/vend',
    title: 'Vend component',
    icon: <CategoryIcon />,
    loader: async () => <VendComponentPage />,
  },
});

const reclaimPage = PageBlueprint.make({
  name: 'reclaim',
  params: {
    path: '/reclaim',
    title: 'Reclaim',
    icon: <RestoreIcon />,
    loader: async () => <ReclaimPage />,
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

const addComponentPage = PageBlueprint.make({
  name: 'add',
  params: {
    path: '/add',
    title: 'Add component',
    icon: <LibraryAddIcon />,
    loader: async () => <AddComponentPage />,
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

const opsPage = PageBlueprint.make({
  name: 'ops',
  params: {
    path: '/ops',
    title: 'Ops',
    icon: <BuildIcon />,
    loader: async () => <OpsPage />,
  },
});

const standardsPage = PageBlueprint.make({
  name: 'standards',
  params: {
    path: '/standards',
    title: 'Standards',
    icon: <MenuBookIcon />,
    loader: async () => <StandardsPage />,
  },
});

const campaignsPage = PageBlueprint.make({
  name: 'campaigns',
  params: {
    path: '/campaigns',
    title: 'Campaigns',
    icon: <NewReleasesIcon />,
    loader: async () => <CampaignsPage />,
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

const importBatchPage = PageBlueprint.make({
  name: 'import-batch',
  params: {
    path: '/import/batch',
    title: 'Batch import',
    icon: <PlaylistAddIcon />,
    loader: async () => <ImportBatchPage />,
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

const metricsPage = PageBlueprint.make({
  name: 'adoption',
  params: {
    path: '/adoption',
    title: 'Adoption',
    icon: <AssessmentIcon />,
    loader: async () => <MetricsPage />,
  },
});

const roadmapPage = PageBlueprint.make({
  name: 'roadmap',
  params: {
    path: '/roadmap',
    title: 'Roadmap evidence',
    icon: <FlagIcon />,
    loader: async () => <RoadmapPage />,
  },
});

const activityPage = PageBlueprint.make({
  name: 'activity',
  params: {
    path: '/activity',
    title: 'Activity',
    icon: <TimelineIcon />,
    loader: async () => <ActivityPage />,
  },
});

const maturityPage = PageBlueprint.make({
  name: 'maturity',
  params: {
    path: '/maturity',
    title: 'Maturity',
    icon: <BarChartIcon />,
    loader: async () => <MaturityPage />,
  },
});

const compliancePage = PageBlueprint.make({
  name: 'compliance',
  params: {
    path: '/compliance',
    title: 'Compliance',
    icon: <SecurityIcon />,
    loader: async () => <CompliancePage />,
  },
});

const valueStreamPage = PageBlueprint.make({
  name: 'value-stream',
  params: {
    path: '/value-stream',
    title: 'Value stream',
    icon: <ShowChartIcon />,
    loader: async () => <ValueStreamPage />,
  },
});

const feedbackPage = PageBlueprint.make({
  name: 'feedback',
  params: {
    path: '/feedback',
    title: 'Feedback',
    icon: <FeedbackIcon />,
    loader: async () => <FeedbackPage />,
  },
});

const finopsPage = PageBlueprint.make({
  name: 'finops',
  params: {
    path: '/finops',
    title: 'FinOps',
    icon: <AccountBalanceIcon />,
    loader: async () => <FinOpsPage />,
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
    vendComponentPage,
    reclaimPage,
    runsPage,
    upgradePage,
    addComponentPage,
    fleetPage,
    opsPage,
    standardsPage,
    campaignsPage,
    importPage,
    importBatchPage,
    verifyPage,
    estatePage,
    metricsPage,
    roadmapPage,
    activityPage,
    maturityPage,
    compliancePage,
    valueStreamPage,
    feedbackPage,
    finopsPage,
    repaveLineageCard,
  ],
});
