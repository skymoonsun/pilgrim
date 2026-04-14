import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { jobsApi } from '../../api/client';
import type { CrawlJob } from '../../api/client';
import { IconRefresh, IconEye, IconClipboard } from '../../components/icons/Icons';

export default function Jobs() {
  const [jobs, setJobs] = useState<CrawlJob[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadJobs();
  }, []);

  async function loadJobs() {
    setLoading(true);
    try {
      const res = await jobsApi.list(0, 100);
      setJobs(res.items);
      setTotal(res.total);
    } catch (err) {
      console.error('Failed to load jobs:', err);
    }
    setLoading(false);
  }

  if (loading) {
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
        <button className="btn btn-secondary" onClick={loadJobs}>
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
              jobs.map((job) => (
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
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
