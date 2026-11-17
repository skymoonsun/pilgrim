/**
 * c4game admin panel link (the "Save to Admin" CTA).
 *
 * The CTA opens the admin panel's source-onboarding dialog on the
 * pilgrim config we came from:
 *   `{ADMIN_BASE}/sources?new=pilgrim&config_id=<crawl-config-uuid>`
 *
 * ADMIN_BASE composition mirrors c4game-core's `ui_base_url()`
 * (app/services/pilgrim.py: API :8000 → UI :3000, :8011 → :3011) on the
 * reverse path: pilgrim UI :3000 (prod) → admin :3030, :3011 (e2e) →
 * admin :3031, on the same host. Set `VITE_ADMIN_BASE_URL` (build time,
 * Vite bakes it into the bundle) to point at a host where the panel is
 * not colocated.
 */

const ADMIN_PORT_BY_UI_PORT: Record<string, string> = {
  '3000': '3030',
  '3011': '3031',
};

/** Admin panel origin for the current pilgrim UI origin. */
export function adminBaseUrl(): string {
  const fromEnv = import.meta.env.VITE_ADMIN_BASE_URL?.trim().replace(/\/+$/, '');
  if (fromEnv) return fromEnv;
  const { protocol, hostname, port } = window.location;
  const adminPort = ADMIN_PORT_BY_UI_PORT[port] ?? '3030';
  return `${protocol}//${hostname}:${adminPort}`;
}

/** "Save to Admin" target: opens the onboarding dialog pre-picking `configId`. */
export function adminSaveSourceUrl(configId: string): string {
  return `${adminBaseUrl()}/sources?new=pilgrim&config_id=${encodeURIComponent(configId)}`;
}
