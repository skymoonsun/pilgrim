import { useState } from 'react';
import { Link } from 'react-router-dom';
import { activitiesApi } from '../../api/client';
import type { ActivityItem, ActivityType, CrawlJobActivity, ProxyFetchActivity, ProxyValidationActivity } from '../../api/client';
import { IconRefresh, IconEye, IconClipboard } from '../../components/icons/Icons';
import { useInfiniteScroll } from '../../hooks/useInfiniteScroll';

const TYPE_TABS: { label: string; value: ActivityType | '' }[] = [
  { label: 'All', value: '' },
  { label: 'Crawls', value: 'crawl_job' },
  { label: 'Fetches', value: 'proxy_fetch' },
  { label: 'Validations', value: 'proxy_validation' },
];

function statusBadgeClass(status: string): string {
  if (status === 'success' || status === 'succeeded') return 'success';
  if (status === 'error' || status === 'failed') return 'failed';
  if (status === 'running' || status === 'warning') return 'running';
  if (status === 'queued') return 'queued';
  return 'cancelled';
}

function typeBadgeClass(type: ActivityType): string {
  if (type === 'crawl_job') return 'success';
  if (type === 'proxy_fetch') return 'running';
  return 'queued';
}

function typeLabel(type: ActivityType): string {
  if (type === 'crawl_job') return 'Crawl';
  if (type === 'proxy_fetch') return 'Fetch';
  return 'Validate';
}

function formatDuration(ms: number | null): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTime(dt: string | null): string {
  if (!dt) return '—';
  return new Date(dt).toLocaleString();
}

function ActivityRow({ item }: { item: ActivityItem }) {
  if (item.type === 'crawl_job') {
    const j = item as CrawlJobActivity;
    const duration = j.started_at && j.finished_at
      ? formatDuration(new Date(j.finished_at).getTime() - new Date(j.started_at).getTime())
      : '—';
    return (
      <tr>
        <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{j.id.slice(0, 8)}</td>
        <td><span className={`badge badge--${typeBadgeClass(j.type)}`}>{typeLabel(j.type)}</span></td>
        <td style={{ maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{j.target_url}</td>
        <td><span className={`badge badge--${statusBadgeClass(j.status)}`}>{j.status}</span></td>
        <td>{formatTime(j.started_at)}</td>
        <td>{formatTime(j.finished_at)}</td>
        <td>{duration}</td>
        <td>
          <div className="action-btns">
            <Link to={`/jobs/${j.id}`} className="action-btn" title="View Details">
              <IconEye size={16} />
            </Link>
          </div>
        </td>
      </tr>
    );
  }

  if (item.type === 'proxy_fetch') {
    const f = item as ProxyFetchActivity;
    const finishedAt = new Date(new Date(f.created_at).getTime() + f.duration_ms).toISOString();
    return (
      <tr>
        <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{f.id.slice(0, 8)}</td>
        <td><span className={`badge badge--${typeBadgeClass(f.type)}`}>{typeLabel(f.type)}</span></td>
        <td style={{ maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {f.source_name || 'Proxy Source'} — {f.proxies_found} found, {f.proxies_new} new
        </td>
        <td><span className={`badge badge--${statusBadgeClass(f.status)}`}>{f.status}</span></td>
        <td>{formatTime(f.created_at)}</td>
        <td>{formatTime(finishedAt)}</td>
        <td>{formatDuration(f.duration_ms)}</td>
        <td></td>
      </tr>
    );
  }

  if (item.type === 'proxy_validation') {
    const v = item as ProxyValidationActivity;
    const finishedAt = new Date(new Date(v.created_at).getTime() + v.duration_ms).toISOString();
    return (
      <tr>
        <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>{v.id.slice(0, 8)}</td>
        <td><span className={`badge badge--${typeBadgeClass(v.type)}`}>{typeLabel(v.type)}</span></td>
        <td style={{ maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {v.source_name || 'Proxy Source'} — {v.proxies_healthy}/{v.proxies_tested} healthy
        </td>
        <td><span className={`badge badge--${statusBadgeClass(v.status)}`}>{v.status}</span></td>
        <td>{formatTime(v.created_at)}</td>
        <td>{formatTime(finishedAt)}</td>
        <td>{formatDuration(v.duration_ms)}</td>
        <td></td>
      </tr>
    );
  }

  return null;
}

export default function Jobs() {
  const [typeFilter, setTypeFilter] = useState<ActivityType | ''>('');

  const { items: activities, total, loading, loadingMore, sentinelRef, reset } = useInfiniteScroll<ActivityItem>({
    fetchPage: (skip, limit) =>
      activitiesApi.list({
        type: typeFilter ? [typeFilter as ActivityType] : undefined,
        skip,
        limit,
      }),
    pageSize: 50,
    deps: [typeFilter],
  });

  if (loading && activities.length === 0) {
    return (
      <div className="loading-overlay">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Jobs</h1>
          <p className="page-subtitle">{total} total activit{total !== 1 ? 'ies' : 'y'}</p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {TYPE_TABS.map((tab) => (
            <button
              key={tab.value}
              className={`btn ${typeFilter === tab.value ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setTypeFilter(tab.value)}
              style={{ padding: '4px 12px', fontSize: '0.8rem' }}
            >
              {tab.label}
            </button>
          ))}
          <button className="btn btn-secondary" onClick={reset} style={{ marginLeft: 8 }}>
            <IconRefresh size={16} /> Refresh
          </button>
        </div>
      </div>

      <div className="card table-card">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Type</th>
              <th>Detail</th>
              <th>Status</th>
              <th>Started</th>
              <th>Finished</th>
              <th>Duration</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {activities.length === 0 ? (
              <tr>
                <td colSpan={8}>
                  <div className="empty-state">
                    <div className="empty-state-icon"><IconClipboard size={48} /></div>
                    <div className="empty-state-text">No activities found</div>
                    <div className="empty-state-sub">
                      Activities appear here when crawl jobs or proxy tasks run
                    </div>
                  </div>
                </td>
              </tr>
            ) : (
              <>
                {activities.map((item) => (
                  <ActivityRow key={`${item.type}-${item.id}`} item={item} />
                ))}
                <tr ref={sentinelRef as any}>
                  <td colSpan={8} style={{ textAlign: 'center', padding: '16px 0', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                    {loadingMore && <div className="spinner" style={{ margin: '0 auto' }} />}
                    {!loadingMore && activities.length < total && <span>Scroll to load more...</span>}
                    {!loadingMore && activities.length >= total && total > 0 && <span>All activities loaded</span>}
                  </td>
                </tr>
              </>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}