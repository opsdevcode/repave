import { hasRepaveLineage } from './RepaveLineageCard';

describe('hasRepaveLineage', () => {
  it('is true when the blueprint annotation is present', () => {
    expect(hasRepaveLineage({ 'repave.dev/blueprint': 'terraform-module-generic' })).toBe(
      true,
    );
  });

  it('is false without lineage annotations', () => {
    expect(hasRepaveLineage({})).toBe(false);
    expect(hasRepaveLineage(undefined)).toBe(false);
  });
});
