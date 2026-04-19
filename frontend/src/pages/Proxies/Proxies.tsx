import { useEffect, useState } from 'react';
import { proxyApi } from '../../api/client';
import type { ValidProxy } from '../../api/client';
import { IconShield, IconTrash } from '../../components/icons/Icons';

export default function Proxies() {
  const [proxies, setProxies] = useState<ValidProxy[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [healthFilter, setHealthFilter] = useState('');
  const [protocolFilter, setProtocolFilter] = useState('');

  useEffect(() => {
    loadProxies();
  }, [healthFilter, protocolFilter]);

  async function loadProxies() {
    setLoading(true);
    try {
      const res = await proxyApi.list({
        health: healthFilter || undefined,
        protocol: protocolFilter || undefined,
        limit: 200,
      });
      setProxies(res.items);
      setTotal(res.total);
    } catch (err) {
      console.error('Failed to load proxies:', err);
    }
    setLoading(false);
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this proxy?')) return;
    try {
      await proxyApi.delete(id);
      setProxies((prev) => prev.filter((p) => p.id !== id));
      setTotal((prev) => prev - 1);
    } catch (err) {
      alert(`Failed to delete: ${err instanceof Error ? err.message : err}`);
    }
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
          <h1 className="page-title">Valid Proxies</h1>
          <p className="page-subtitle">{total} prox{total !== 1 ? 'ies' : 'y'} total</p>
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <select
            className="form-input form-select"
            value={healthFilter}
            onChange={(e) => setHealthFilter(e.target.value)}
            style={{ width: 140 }}
          >
            <option value="">All health</option>
            <option value="healthy">Healthy</option>
            <option value="degraded">Degraded</option>
            <option value="unhealthy">Unhealthy</option>
          </select>
          <select
            className="form-input form-select"
            value={protocolFilter}
            onChange={(e) => setProtocolFilter(e.target.value)}
            style={{ width: 120 }}
          >
            <option value="">All protocols</option>
            <option value="http">HTTP</option>
            <option value="https">HTTPS</option>
            <option value="socks4">SOCKS4</option>
            <option value="socks5">SOCKS5</option>
          </select>
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
              <th>Avg Response</th>
              <th>Success / Fail</th>
              <th>Last Checked</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {proxies.length === 0 ? (
              <tr>
                <td colSpan={8}>
                  <div className="empty-state">
                    <div className="empty-state-icon"><IconShield size={48} /></div>
                    <div className="empty-state-text">No proxies found</div>
                    <div className="empty-state-sub">
                      Add a proxy source and fetch proxies to see them here
                    </div>
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
                  <td style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                    <span style={{ color: 'var(--status-success)' }}>{proxy.success_count}</span>
                    {' / '}
                    <span style={{ color: 'var(--status-failed)' }}>{proxy.failure_count}</span>
                  </td>
                  <td style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                    {proxy.last_checked_at ? new Date(proxy.last_checked_at).toLocaleString() : '—'}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="action-btn action-btn--delete"
                      title="Delete"
                      onClick={() => handleDelete(proxy.id)}
                    >
                      <IconTrash size={16} />
                    </button>
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