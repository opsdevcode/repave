import { createFrontendModule } from '@backstage/frontend-plugin-api';
import { AppRootWrapperBlueprint, ThemeBlueprint } from '@backstage/plugin-app-react';
import { UnifiedThemeProvider } from '@backstage/theme';
import Brightness2Icon from '@material-ui/icons/Brightness2';
import { ReactNode } from 'react';
import { nightOpsTheme } from '../../theme/nightOps';
import { PortalAppBar } from './PortalAppBar';

const nightOpsThemeExtension = ThemeBlueprint.make({
  name: 'night-ops',
  params: {
    theme: {
      id: 'night-ops',
      title: 'Night-ops',
      variant: 'dark',
      icon: <Brightness2Icon />,
      Provider: ({ children }) => (
        <UnifiedThemeProvider theme={nightOpsTheme}>{children}</UnifiedThemeProvider>
      ),
    },
  },
});

function PortalChrome({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
      }}
    >
      <PortalAppBar />
      <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>{children}</div>
    </div>
  );
}

const portalChromeWrapper = AppRootWrapperBlueprint.make({
  name: 'portal-chrome',
  params: {
    component: PortalChrome,
  },
});

export const chromeModule = createFrontendModule({
  pluginId: 'app',
  extensions: [nightOpsThemeExtension, portalChromeWrapper],
});
