export interface Config {
  repave?: {
    /**
     * Night-ops workbench base (HTML portal). Hosted same-host is `/`.
     * @visibility frontend
     */
    portalBaseUrl?: string;
    /**
     * Optional white-label mark (http(s) or root-relative).
     * @visibility frontend
     */
    logoUrl?: string;
    /**
     * Optional white-label accent hex (for example #F59E0B).
     * @visibility frontend
     */
    accentColor?: string;
  };
}
