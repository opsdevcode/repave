import { render, waitFor } from '@testing-library/react';
import apiDocsPlugin from '@backstage/plugin-api-docs/alpha';
import catalogGraphPlugin from '@backstage/plugin-catalog-graph/alpha';
import catalogImportPlugin from '@backstage/plugin-catalog-import/alpha';
import kubernetesPlugin from '@backstage/plugin-kubernetes/alpha';
import orgPlugin from '@backstage/plugin-org/alpha';
import searchPlugin from '@backstage/plugin-search/alpha';
import techdocsPlugin from '@backstage/plugin-techdocs/alpha';
import App, { appFeatures } from './App';

describe('App', () => {
  it('should render', async () => {
    process.env = {
      NODE_ENV: 'test',
      APP_CONFIG: [
        {
          data: {
            app: { title: 'Test' },
            backend: { baseUrl: 'http://localhost:7007' },
            techdocs: {
              storageUrl: 'http://localhost:7007/api/techdocs/static/docs',
            },
          },
          context: 'test',
        },
      ] as any,
    };

    const rendered = render(App.createRoot());

    await waitFor(() => {
      expect(rendered.baseElement).toBeInTheDocument();
    });
  });

  it('registers catalog IDP plugins so graph, search, docs, import, org, and kubernetes work', () => {
    expect(appFeatures).toEqual(
      expect.arrayContaining([
        catalogGraphPlugin,
        catalogImportPlugin,
        apiDocsPlugin,
        searchPlugin,
        techdocsPlugin,
        orgPlugin,
        kubernetesPlugin,
      ]),
    );
  });
});
