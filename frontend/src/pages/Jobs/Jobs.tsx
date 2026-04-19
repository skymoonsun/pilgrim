import { Link } from 'react-router-dom';
import { jobsApi } from '../../api/client';
import type { CrawlJob } from '../../api/client';
import { IconRefresh, IconEye, IconClipboard } from '../../components/icons/Icons';
import { useInfiniteScroll } from '../../hooks/useInfiniteScroll';

export default function Jobs() {
  const { items: jobs, total, loading, loadingMore, sentinelRef, reset } = useInfiniteScroll<CrawlJob>({
    fetchPage: (skip, limit) => jobsApi.list(skip, limit),
    pageSize: 50,
  });

  if (loading && jobs.length === 0) {
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
          <h1 className="page-title">Crawl Jobs</h1>
          <p className="page-subtitle">{total} total job{total !== 1 ? 's' : ''}</p>
        </div>
        <button className="btn btn-secondary" onClick={reset}>
          <IconRefresh size={16} /> Refresh
        </button>
      </div>

      <div className="card table-card">
        <table>
          <thead>
            <tr>
              <th>Job ID</th>
              <th>Target URL</th>
              <th>Status</th>
              <th>Queue</th>
              <th>Priority</th>
              <th>Started</th>
              <th>Finished</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {jobs.length === 0 ? (
              <tr>
                <td colSpan={8}>
                  <div className="empty-state">
                    <div className="empty-state-icon"><IconClipboard size={48} /></div>
                    <div className="empty-state-text">No crawl jobs found</div>
                    <div className="empty-state-sub">
                      Jobs appear here when you trigger async crawls
                    </div>
                  </div>
                </td>
              </tr>
            ) : (
              <>
                {jobs.map((job) => (
                  <tr key={job.id}>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
                      {job.id.slice(0, 8)}
                    </td>
                    <td
                      style={{
                        maxWidth: 240,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {job.target_url}
                    </td>
                    <td>
                      <span className={`badge badge--${job.status}`}>{job.status}</span>
                    </td>
                    <td>{job.queue}</td>
                    <td>{job.priority}</td>
                    <td>
                      {job.started_at
                        ? new Date(job.started_at).toLocaleString()
                        : '—'}
                    </td>
                    <td>
                      {job.finished_at
                        ? new Date(job.finished_at).toLocaleString()
                        : '—'}
                    </td>
                    <td>
                      <div className="action-btns">
                        <Link to={`/jobs/${job.id}`} className="action-btn" title="View Details">
                          <IconEye size={16} />
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
                <tr ref={sentinelRef as any}>
                  <td colSpan={8} style={{ textAlign: 'center', padding: '16px 0', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                    {loadingMore && <div className="spinner" style={{ margin: '0 auto' }} />}
                    {!loadingMore && jobs.length < total && <span>Scroll to load more...</span>}
                    {!loadingMore && jobs.length >= total && total > 0 && <span>All jobs loaded</span>}
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