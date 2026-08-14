export interface Config {
  repave?: {
    /** Base URL of the repave API (no trailing slash), e.g. http://repave:8088 */
    apiBaseUrl?: string;
    /** Bearer token for /api/v2 when auth.service_mode is on */
    apiToken?: string;
  };
}
