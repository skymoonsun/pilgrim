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

// ── Schedule types ───────────────────────────────────────

export interface ScheduleUrlTarget {
  id: string;
  url: string;
  label: string | null;
  is_active: boolean;
  created_at: string;
}

export interface ScheduleConfigLink {
  id: string;
  config_id: string;
  config_name: string | null;
  priority: number;
}

export interface CallbackConfig {
  id: string;
  schedule_id: string;
  url: string;
  method: string;
  headers: Record<string, string> | null;
  field_mapping: Record<string, unknown>;
  include_metadata: boolean;
  batch_results: boolean;
  retry_count: number;
  retry_delay_seconds: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CallbackLog {
  id: string;
  callback_config_id: string;
  crawl_job_id: string | null;
  schedule_id: string;
  request_url: string;
  request_method: string;
  request_body: Record<string, unknown> | null;
  response_status: number | null;
  response_body: string | null;
  success: boolean;
  error_message: string | null;
  duration_ms: number;
  attempt_number: number;
  created_at: string;
}

export interface Schedule {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  timezone: string;
  cron_expression: string | null;
  interval_seconds: number | null;
  default_queue: string;
  next_run_at: string | null;
  last_run_at: string | null;
  run_count: number;
  created_at: string;
  updated_at: string;
  config_links: ScheduleConfigLink[];
  url_targets: ScheduleUrlTarget[];
  callback: CallbackConfig | null;
}

export interface ScheduleListResponse {
  items: Schedule[];
  total: number;
}

export interface ScheduleCreateData {
  name: string;
  description?: string | null;
  timezone?: string;
  cron_expression?: string | null;
  interval_seconds?: number | null;
  default_queue?: string;
  config_ids?: string[];
  urls?: { url: string; label?: string | null }[];
  callback?: {
    url: string;
    method?: string;
    headers?: Record<string, string> | null;
    field_mapping?: Record<string, unknown>;
    include_metadata?: boolean;
    batch_results?: boolean;
    retry_count?: number;
    retry_delay_seconds?: number;
  } | null;
}

export interface TriggerResponse {
  schedule_id: string;
  jobs_created: number;
  job_ids: string[];
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
  if (res.status === 204) return undefined as T;
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

// ── Schedules ─────────────────────────────────────────────

export const schedulesApi = {
  list: (skip = 0, limit = 50, activeOnly = false) =>
    request<ScheduleListResponse>(
      `/schedules/?skip=${skip}&limit=${limit}&active_only=${activeOnly}`
    ),

  get: (id: string) => request<Schedule>(`/schedules/${id}`),

  create: (data: ScheduleCreateData) =>
    request<Schedule>('/schedules/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: Partial<Schedule>) =>
    request<Schedule>(`/schedules/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request<void>(`/schedules/${id}`, { method: 'DELETE' }),

  trigger: (id: string) =>
    request<TriggerResponse>(`/schedules/${id}/trigger`, { method: 'POST' }),

  // URL management
  addUrl: (scheduleId: string, data: { url: string; label?: string | null }) =>
    request<ScheduleUrlTarget>(`/schedules/${scheduleId}/urls`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  removeUrl: (scheduleId: string, urlId: string) =>
    request<void>(`/schedules/${scheduleId}/urls/${urlId}`, {
      method: 'DELETE',
    }),

  // Callback management
  setCallback: (scheduleId: string, data: Omit<CallbackConfig, 'id' | 'schedule_id' | 'created_at' | 'updated_at'>) =>
    request<CallbackConfig>(`/schedules/${scheduleId}/callback`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  removeCallback: (scheduleId: string) =>
    request<void>(`/schedules/${scheduleId}/callback`, {
      method: 'DELETE',
    }),

  getCallbackLogs: (scheduleId: string, skip = 0, limit = 50) =>
    request<CallbackLog[]>(
      `/schedules/${scheduleId}/callback/logs?skip=${skip}&limit=${limit}`
    ),
};
