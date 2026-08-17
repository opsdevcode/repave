import { render, waitFor } from '@testing-library/react';
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

  it('registers TechDocs so the entity Docs tab can appear', () => {
    expect(appFeatures).toContain(techdocsPlugin);
  });
});
