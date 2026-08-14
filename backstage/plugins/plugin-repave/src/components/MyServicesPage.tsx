import { useEffect, useState } from 'react';
import {
  Content,
  Header,
  Link,
  Page,
  Progress,
  Table,
  type TableColumn,
} from '@backstage/core-components';
import { useApi } from '@backstage/frontend-plugin-api';
import type { Entity } from '@backstage/catalog-model';
import { catalogApiRef } from '@backstage/plugin-catalog-react';
import { hasRepaveLineage } from './RepaveLineageCard';

export type RepaveServiceRow = {
  name: string;
  namespace: string;
  title: string;
  owner: string;
  blueprint: string;
  blueprintVersion: string;
};

export function rowsFromEntities(entities: Entity[]): RepaveServiceRow[] {
  return entities
    .filter(entity => hasRepaveLineage(entity.metadata.annotations))
    .map(entity => {
      const annotations = entity.metadata.annotations ?? {};
      return {
        name: entity.metadata.name,
        namespace: entity.metadata.namespace ?? 'default',
        title: String(entity.metadata.title ?? entity.metadata.name),
        owner: String(entity.spec?.owner ?? ''),
        blueprint: annotations['repave.dev/blueprint'] ?? '',
        blueprintVersion: annotations['repave.dev/blueprint-version'] ?? '',
      };
    })
    .sort((left, right) => left.title.localeCompare(right.title));
}

const COLUMNS: TableColumn<RepaveServiceRow>[] = [
  {
    title: 'Service',
    field: 'title',
    render: row => (
      <Link to={`/catalog/${row.namespace}/component/${row.name}`}>{row.title}</Link>
    ),
  },
  { title: 'Owner', field: 'owner' },
  { title: 'Blueprint', field: 'blueprint' },
  { title: 'Version', field: 'blueprintVersion' },
];

export function MyServicesPage() {
  const catalogApi = useApi(catalogApiRef);
  const [rows, setRows] = useState<RepaveServiceRow[] | undefined>();
  const [error, setError] = useState<string>('');

  useEffect(() => {
    let cancelled = false;
    catalogApi
      .getEntities({ filter: { kind: 'Component' } })
      .then(result => {
        if (!cancelled) {
          setRows(rowsFromEntities(result.items));
        }
      })
      .catch(err => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [catalogApi]);

  return (
    <Page themeId="home">
      <Header
        title="My services"
        subtitle="Golden-path components with repave lineage"
      />
      <Content>
        {error ? <p>{error}</p> : null}
        {rows === undefined && !error ? <Progress /> : null}
        {rows ? (
          <Table
            options={{ paging: rows.length > 20, search: true, padding: 'dense' }}
            columns={COLUMNS}
            data={rows}
            emptyContent={
              <p>
                No golden-path services yet.{' '}
                <Link to="/create">Create one from a template</Link>.
              </p>
            }
          />
        ) : null}
      </Content>
    </Page>
  );
}
