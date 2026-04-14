/** API base URL — proxied via Vite in dev */
const API_BASE = '/api/v1';

export interface CrawlConfig {
  id: string;
  name: string;
  description: string | null;
  scraper_profile: string;
  fetch_options: Record<string, unknown> | null;
  extraction_spec: Record<string, unknown> | null;
  spider_entrypoint: string | null;
  use_proxy: boolean;
  rotate_user_agent: boolean;
  custom_headers: Record<string, string> | null;
  custom_delay: number | null;
  max_concurrent: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CrawlConfigListResponse {
  items: CrawlConfig[];
  total: number;
}

export interface CrawlJob {
  id: string;
  crawl_configuration_id: string;
  target_url: string;
  status: string;
  queue: string;
  priority: number;
  celery_task_id: string | null;
  result_summary: Record<string, unknown> | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CrawlJobListResponse {
  items: CrawlJob[];
  total: number;
}

export interface ScrapeRequest {
  config_id: string;
  url: string;
}

export interface ScrapeResponse {
  config_id: string;
  url: string;
  http_status: number | null;
  data: Record<string, unknown> | null;
  error: string | null;
  duration_ms: number;
}

export interface HealthResponse {
  status: string;
  environment?: string;
  version?: string;
}

export interface ReadinessResponse {
  status: string;
  database: string;
  redis: string;
}

// ── Generic fetch helper ─────────────────────────────────

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

// ── Health ────────────────────────────────────────────────

export const healthApi = {
  liveness: () => request<HealthResponse>('/health/'),
  readiness: () => request<ReadinessResponse>('/health/readiness'),
};

// ── Crawl Configs ─────────────────────────────────────────

export const configsApi = {
  list: (skip = 0, limit = 50, activeOnly = false) =>
    request<CrawlConfigListResponse>(
      `/crawl-configs/?skip=${skip}&limit=${limit}&active_only=${activeOnly}`
    ),

  get: (id: string) => request<CrawlConfig>(`/crawl-configs/${id}`),

  create: (data: Partial<CrawlConfig>) =>
    request<CrawlConfig>('/crawl-configs/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: Partial<CrawlConfig>) =>
    request<CrawlConfig>(`/crawl-configs/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request<void>(`/crawl-configs/${id}`, { method: 'DELETE' }),
};

// ── Scrape ────────────────────────────────────────────────

export const scrapeApi = {
  execute: (data: ScrapeRequest) =>
    request<ScrapeResponse>('/scrape/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

// ── Crawl Jobs ────────────────────────────────────────────

export const jobsApi = {
  list: (skip = 0, limit = 50) =>
    request<CrawlJobListResponse>(
      `/crawl/jobs?skip=${skip}&limit=${limit}`
    ),

  get: (id: string) => request<CrawlJob>(`/crawl/jobs/${id}`),

  create: (data: { config_id: string; url: string; queue?: string; priority?: number }) =>
    request<CrawlJob>('/crawl/jobs', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};
