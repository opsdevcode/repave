export function queryParam(search: string, key: string): string {
  const raw = search.startsWith('?') ? search.slice(1) : search;
  return new URLSearchParams(raw).get(key)?.trim() ?? '';
}
