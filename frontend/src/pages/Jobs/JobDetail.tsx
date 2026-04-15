import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { jobsApi, configsApi } from '../../api/client';
import type { CrawlJob } from '../../api/client';
import { IconClipboard, IconRefresh } from '../../components/icons/Icons';

export default function JobDetail() {
  const { id } = useParams<{ id: string }>();
  const [job, setJob] = useState<CrawlJob | null>(null);
  const [configName, setConfigName] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (id) loadJob(id);
  }, [id]);

  async function loadJob(jobId: string) {
    setLoading(true);
    try {
      const res = await jobsApi.get(jobId);
      setJob(res);
      try {
        const cfg = await configsApi.get(res.crawl_configuration_id);
        setConfigName(cfg.name);
      } catch {
        setConfigName(res.crawl_configuration_id.slice(0, 8));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Job not found');
    }
    setLoading(false);
  }

  if (loading) {
    return <div className="loading-overlay"><div className="spinner" /></div>;
  }

  if (error || !job) {
    return (
      <div className="animate-in">
        <div className="card" style={{ padding: 40, textAlign: 'center' }}>
          <div className="empty-state-icon"><IconClipboard size={48} /></div>
          <div className="empty-state-text">{error || 'Job not found'}</div>
          <Link to="/jobs" className="btn btn-secondary" style={{ marginTop: 16 }}>← Back to Jobs</Link>
        </div>
      </div>
    );
  }

  const duration =
    job.started_at && job.finished_at
      ? ((new Date(job.finished_at).getTime() - new Date(job.started_at).getTime()) / 1000).toFixed(2) + 's'
      : '—';

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Job Detail</h1>
          <p className="page-subtitle">{job.id}</p>
        </div>
        <button className="btn btn-secondary" onClick={() => loadJob(job.id)}>
          <IconRefresh size={16} /> Refresh
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        {/* General */}
        <div className="card" style={{ padding: 28 }}>
          <h3 className="card-title" style={{ marginBottom: 20 }}>Job Info</h3>
          <div className="detail-grid">
            <Row label="ID" value={job.id} mono />
            <Row label="Status" value={
              <span className={`badge badge--${job.status}`}>{job.status}</span>
            } />
            <Row label="Target URL" value={
              <a href={job.target_url} target="_blank" rel="noopener noreferrer"
                style={{ color: 'var(--accent-cyan)', wordBreak: 'break-all' }}>
                {job.target_url}
              </a>
            } />
            <Row label="Config" value={
              <Link to={`/configurations/${job.crawl_configuration_id}`}
                style={{ color: 'var(--accent-cyan)' }}>
                {configName}
              </Link>
            } />
            <Row label="Queue" value={job.queue} />
            <Row label="Priority" value={job.priority.toString()} />
            <Row label="Celery Task" value={job.celery_task_id || '—'} mono />
            <Row label="Duration" value={duration} />
            <Row label="Created" value={new Date(job.created_at).toLocaleString()} />
            <Row label="Started" value={job.started_at ? new Date(job.started_at).toLocaleString() : '—'} />
            <Row label="Finished" value={job.finished_at ? new Date(job.finished_at).toLocaleString() : '—'} />
          </div>
        </div>

        {/* Result / Error */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          {job.error_message && (
            <div className="card" style={{ padding: 28 }}>
              <h3 className="card-title" style={{ marginBottom: 20, color: 'var(--status-failed)' }}>Error</h3>
              <pre style={{
                background: 'rgba(255,82,82,0.08)',
                border: '1px solid rgba(255,82,82,0.2)',
                borderRadius: 'var(--radius-md)',
                padding: 16,
                fontSize: '0.8rem',
                fontFamily: 'var(--font-mono)',
                color: 'var(--status-failed)',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                margin: 0,
              }}>
                {job.error_message}
              </pre>
            </div>
          )}

          <div className="card" style={{ padding: 28, flex: 1 }}>
            <h3 className="card-title" style={{ marginBottom: 20 }}>Result Summary</h3>
            {job.result_summary ? (
              <pre style={{
                background: 'var(--bg-tertiary)',
                borderRadius: 'var(--radius-md)',
                padding: 16,
                fontSize: '0.78rem',
                fontFamily: 'var(--font-mono)',
                color: 'var(--text-secondary)',
                overflow: 'auto',
                maxHeight: 500,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                margin: 0,
              }}>
                {JSON.stringify(job.result_summary, null, 2)}
              </pre>
            ) : (
              <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                {job.status === 'queued' || job.status === 'running' ? 'Job is still running...' : 'No result data'}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '10px 0', borderBottom: '1px solid var(--border-subtle)',
    }}>
      <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>{label}</span>
      <span style={{
        color: 'var(--text-primary)',
        fontSize: mono ? '0.78rem' : '0.85rem',
        fontFamily: mono ? 'var(--font-mono)' : 'inherit',
        maxWidth: '60%', textAlign: 'right', wordBreak: 'break-all',
      }}>
        {value}
      </span>
    </div>
  );
}
