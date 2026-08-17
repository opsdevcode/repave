import { readFileSync } from 'fs';
import { resolve } from 'path';

describe('hosted TechDocs generator', () => {
  it('runs mkdocs locally so the image does not need Docker-in-Docker', () => {
    const yaml = readFileSync(
      resolve(__dirname, '../../../app-config.production.yaml'),
      'utf8',
    );
    expect(yaml).toMatch(/runIn:\s*local/);
  });
});
