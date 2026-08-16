import { createFrontendPlugin, PageBlueprint } from '@backstage/frontend-plugin-api';
import { EntityCardBlueprint } from '@backstage/plugin-catalog-react/alpha';
import AccountBalanceIcon from '@material-ui/icons/AccountBalance';
import AppsIcon from '@material-ui/icons/Apps';
import AssessmentIcon from '@material-ui/icons/Assessment';
import AssignmentTurnedInIcon from '@material-ui/icons/AssignmentTurnedIn';
import BarChartIcon from '@material-ui/icons/BarChart';
import CloudDownloadIcon from '@material-ui/icons/CloudDownload';
import DeveloperBoardIcon from '@material-ui/icons/DeveloperBoard';
import FeedbackIcon from '@material-ui/icons/Feedback';
import HistoryIcon from '@material-ui/icons/History';
import MapIcon from '@material-ui/icons/Map';
import SecurityIcon from '@material-ui/icons/Security';
import ShowChartIcon from '@material-ui/icons/ShowChart';
import StorageIcon from '@material-ui/icons/Storage';
import SystemUpdateAltIcon from '@material-ui/icons/SystemUpdateAlt';
import TimelineIcon from '@material-ui/icons/Timeline';
import { ActivityPage } from './components/ActivityPage';
import { CompliancePage } from './components/CompliancePage';
import { EstatePage } from './components/EstatePage';
import { FeedbackPage } from './components/FeedbackPage';
import { FinOpsPage } from './components/FinOpsPage';
import { FleetPage } from './components/FleetPage';
import { ImportPage } from './components/ImportPage';
import { MaturityPage } from './components/MaturityPage';
import { MetricsPage } from './components/MetricsPage';
import { MyServicesPage } from './components/MyServicesPage';
import { RepaveLineageCard } from './components/RepaveLineageCard';
import { RunsPage } from './components/RunsPage';
import { SandboxPage } from './components/SandboxPage';
import { UpgradePage } from './components/UpgradePage';
import { ValueStreamPage } from './components/ValueStreamPage';
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

const metricsPage = PageBlueprint.make({
  name: 'adoption',
  params: {
    path: '/adoption',
    title: 'Adoption',
    icon: <AssessmentIcon />,
    loader: async () => <MetricsPage />,
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
    runsPage,
    upgradePage,
    fleetPage,
    importPage,
    verifyPage,
    estatePage,
    metricsPage,
    activityPage,
    maturityPage,
    compliancePage,
    valueStreamPage,
    feedbackPage,
    finopsPage,
    repaveLineageCard,
  ],
});
