import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { proxySourceApi, proxyApi } from '../../api/client';
import type { ProxySourceConfig, ValidProxy } from '../../api/client';
import { IconRefresh, IconTrash } from '../../components/icons/Icons';

export default function ProxySourceDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [source, setSource] = useState<ProxySourceConfig | null>(null);
  const [proxies, setProxies] = useState<ValidProxy[]>([]);
  const [proxyTotal, setProxyTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);
  const [validating, setValidating] = useState(false);

  useEffect(() => {
    if (id) loadData(id);
  }, [id]);

  async function loadData(sourceId: string) {
    setLoading(true);
    try {
      const [src, proxyRes] = await Promise.all([
        proxySourceApi.get(sourceId),
        proxyApi.list({ source_id: sourceId, limit: 100 }),
      ]);
      setSource(src);
      setProxies(proxyRes.items);
      setProxyTotal(proxyRes.total);
    } catch (err) {
      console.error('Failed to load:', err);
    }
    setLoading(false);
  }

  async function handleFetch() {
    if (!id) return;
    setFetching(true);
    try {
      await proxySourceApi.triggerFetch(id);
      alert('Fetch task queued! Proxies will be updated shortly.');
    } catch (err) {
      alert(`Fetch failed: ${err instanceof Error ? err.message : err}`);
    }
    setFetching(false);
  }

  async function handleValidate() {
    if (!id) return;
    setValidating(true);
    try {
      await proxyApi.triggerValidate(id);
      alert('Validation task queued!');
    } catch (err) {
      alert(`Validation failed: ${err instanceof Error ? err.message : err}`);
    }
    setValidating(false);
  }

  async function handleDelete() {
    if (!id || !source) return;
    if (!confirm(`Delete proxy source "${source.name}" and all its proxies?`)) return;
    try {
      await proxySourceApi.delete(id);
      navigate('/proxy-sources');
    } catch (err) {
      alert(`Failed to delete: ${err instanceof Error ? err.message : err}`);
    }
  }

  if (loading || !source) {
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
          <h1 className="page-title">{source.name}</h1>
          <p className="page-subtitle">{source.description || 'No description'}</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-secondary" onClick={handleFetch} disabled={fetching}>
            <IconRefresh size={16} /> {fetching ? 'Fetching...' : 'Fetch Now'}
          </button>
          <button className="btn btn-secondary" onClick={handleValidate} disabled={validating}>
            <IconRefresh size={16} /> {validating ? 'Validating...' : 'Validate'}
          </button>
          <button className="btn btn-secondary" onClick={handleDelete} style={{ color: 'var(--status-failed)' }}>
            <IconTrash size={16} /> Delete
          </button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 24 }}>
          <div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 4 }}>Source URL</div>
            <div style={{ fontSize: '0.9rem', color: 'var(--text-primary)', wordBreak: 'break-all' }}>
              {source.url}
            </div>
          </div>
          <div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 4 }}>Format</div>
            <span className="badge badge--queued">{source.format_type}</span>
          </div>
          <div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 4 }}>Status</div>
            <span className={`badge badge--${source.is_active ? 'success' : 'cancelled'}`}>
              {source.is_active ? 'Active' : 'Inactive'}
            </span>
          </div>
          <div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 4 }}>Last Fetched</div>
            <div style={{ fontSize: '0.9rem', color: 'var(--text-primary)' }}>
              {source.last_fetched_at ? new Date(source.last_fetched_at).toLocaleString() : 'Never'}
            </div>
          </div>
          <div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 4 }}>Fetch Interval</div>
            <div style={{ fontSize: '0.9rem', color: 'var(--text-primary)' }}>
              {Math.floor(source.fetch_interval_seconds / 60)} min
            </div>
          </div>
          <div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 4 }}>Proxy TTL</div>
            <div style={{ fontSize: '0.9rem', color: 'var(--text-primary)' }}>
              {Math.floor(source.proxy_ttl_seconds / 3600)}h
            </div>
          </div>
        </div>

        {source.last_fetch_error && (
          <div style={{ marginTop: 16, padding: 12, background: 'var(--status-failed-bg)', borderRadius: 'var(--radius-md)', fontSize: '0.85rem', color: 'var(--status-failed)' }}>
            Last fetch error: {source.last_fetch_error}
          </div>
        )}
      </div>

      <div className="page-header" style={{ marginTop: 24 }}>
        <div>
          <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            Valid Proxies
          </h2>
          <p className="page-subtitle">{proxyTotal} prox{proxyTotal !== 1 ? 'ies' : 'y'} found</p>
        </div>
      </div>

      <div className="card table-card">
        <table>
          <thead>
            <tr>
              <th>IP</th>
              <th>Port</th>
              <th>Protocol</th>
              <th>Health</th>
              <th>Response</th>
              <th>Last Checked</th>
            </tr>
          </thead>
          <tbody>
            {proxies.length === 0 ? (
              <tr>
                <td colSpan={6}>
                  <div className="empty-state">
                    <div className="empty-state-text">No proxies yet</div>
                    <div className="empty-state-sub">Click "Fetch Now" to fetch proxies from this source</div>
                  </div>
                </td>
              </tr>
            ) : (
              proxies.map((proxy) => (
                <tr key={proxy.id}>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem' }}>{proxy.ip}</td>
                  <td style={{ fontFamily: 'var(--font-mono)' }}>{proxy.port}</td>
                  <td><span className="badge badge--queued">{proxy.protocol}</span></td>
                  <td>
                    <span className={`badge badge--${
                      proxy.health === 'healthy' ? 'success' :
                      proxy.health === 'degraded' ? 'running' : 'failed'
                    }`}>
                      {proxy.health}
                    </span>
                  </td>
                  <td style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    {proxy.avg_response_ms != null ? `${Math.round(proxy.avg_response_ms)}ms` : '—'}
                  </td>
                  <td style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                    {proxy.last_checked_at ? new Date(proxy.last_checked_at).toLocaleString() : '—'}
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