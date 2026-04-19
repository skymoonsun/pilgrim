import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { proxySourceApi, proxyApi } from '../../api/client';
import type { ProxySourceConfig, ValidProxy, ProxyFetchLog, ProxyValidationLog } from '../../api/client';
import { IconRefresh, IconTrash, IconEdit, IconClock, IconCheck } from '../../components/icons/Icons';
import { useInfiniteScroll } from '../../hooks/useInfiniteScroll';

export default function ProxySourceDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [source, setSource] = useState<ProxySourceConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);
  const [validating, setValidating] = useState(false);

  // Logs
  const [fetchLogs, setFetchLogs] = useState<ProxyFetchLog[]>([]);
  const [fetchLogsTotal, setFetchLogsTotal] = useState(0);
  const [validationLogs, setValidationLogs] = useState<ProxyValidationLog[]>([]);
  const [validationLogsTotal, setValidationLogsTotal] = useState(0);
  const [expandedLog, setExpandedLog] = useState<string | null>(null);

  const { items: proxies, total: proxyTotal, loadingMore, sentinelRef, reset } = useInfiniteScroll<ValidProxy>({
    fetchPage: (skip, limit) => proxyApi.list({ source_id: id!, skip, limit }),
    pageSize: 50,
    deps: [id],
  });

  useEffect(() => {
    if (id) loadSource(id);
  }, [id]);

  async function loadSource(sourceId: string) {
    setLoading(true);
    try {
      const [src, flRes, vlRes] = await Promise.all([
        proxySourceApi.get(sourceId),
        proxySourceApi.getFetchLogs(sourceId, 0, 10),
        proxySourceApi.getValidationLogs(sourceId, 0, 10),
      ]);
      setSource(src);
      setFetchLogs(flRes.items);
      setFetchLogsTotal(flRes.total);
      setValidationLogs(vlRes.items);
      setValidationLogsTotal(vlRes.total);
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
      alert('Fetch + validate task queued! Results will appear in logs shortly.');
      // Reload after a delay to let tasks complete
      setTimeout(() => loadSource(id), 5000);
    } catch (err) {
      alert(`Fetch failed: ${err instanceof Error ? err.message : err}`);
    }
    setFetching(false);
  }

  async function handleRevalidate() {
    if (!id) return;
    setValidating(true);
    try {
      await proxyApi.triggerValidate(id);
      alert('Re-validation task queued!');
      setTimeout(() => loadSource(id), 5000);
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

  function healthBadge(health: string) {
    const cls = health === 'healthy' ? 'success' : health === 'degraded' ? 'running' : health === 'pending' ? 'queued' : 'failed';
    return <span className={`badge badge--${cls}`}>{health}</span>;
  }

  if (loading || !source) {
    return (
      <div className="loading-overlay">
        <div className="spinner" />
      </div>
    );
  }

  // Compute summary stats from latest validation log
  const latestValidation = validationLogs[0];
  const latestFetch = fetchLogs[0];

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">{source.name}</h1>
          <p className="page-subtitle">{source.description || 'No description'}</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Link to={`/proxy-sources/${id}/edit`} className="btn btn-secondary">
            <IconEdit size={16} /> Edit
          </Link>
          <button className="btn btn-secondary" onClick={handleFetch} disabled={fetching}>
            <IconRefresh size={16} /> {fetching ? 'Fetching...' : 'Fetch Now'}
          </button>
          <button className="btn btn-secondary" onClick={handleRevalidate} disabled={validating}>
            <IconCheck size={16} /> {validating ? 'Validating...' : 'Re-validate'}
          </button>
          <button className="btn btn-secondary" onClick={handleDelete} style={{ color: 'var(--status-failed)' }}>
            <IconTrash size={16} /> Delete
          </button>
        </div>
      </div>

      {/* Config card */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 24 }}>
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
          <div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 4 }}>Max Proxies</div>
            <div style={{ fontSize: '0.9rem', color: 'var(--text-primary)' }}>
              {source.max_proxies != null ? source.max_proxies : 'Unlimited'}
            </div>
          </div>
          <div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 4 }}>Total Proxies</div>
            <div style={{ fontSize: '0.9rem', color: 'var(--text-primary)' }}>
              {proxyTotal}
            </div>
          </div>
        </div>

        {source.last_fetch_error && (
          <div style={{ marginTop: 16, padding: 12, background: 'var(--status-failed-bg)', borderRadius: 'var(--radius-md)', fontSize: '0.85rem', color: 'var(--status-failed)' }}>
            Last fetch error: {source.last_fetch_error}
          </div>
        )}
      </div>

      {/* Summary stats from latest validation */}
      {latestValidation && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 16, marginBottom: 24 }}>
          <StatCard label="Tested" value={latestValidation.proxies_tested} />
          <StatCard label="Healthy" value={latestValidation.proxies_healthy} color="var(--status-success)" />
          <StatCard label="Degraded" value={latestValidation.proxies_degraded} color="var(--status-running)" />
          <StatCard label="Unhealthy" value={latestValidation.proxies_unhealthy} color="var(--status-failed)" />
          <StatCard label="Removed" value={latestValidation.proxies_removed} color="var(--status-failed)" />
        </div>
      )}

      {/* Valid Proxies table */}
      <div className="page-header" style={{ marginTop: 8 }}>
        <div>
          <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            Valid Proxies
          </h2>
          <p className="page-subtitle">{proxyTotal} prox{proxyTotal !== 1 ? 'ies' : 'y'}</p>
        </div>
      </div>

      <div className="card table-card" style={{ marginBottom: 24 }}>
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
              <>
                {proxies.map((proxy) => (
                  <tr key={proxy.id}>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem' }}>{proxy.ip}</td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{proxy.port}</td>
                    <td><span className="badge badge--queued">{proxy.protocol}</span></td>
                    <td>{healthBadge(proxy.health)}</td>
                    <td style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                      {proxy.avg_response_ms != null ? `${Math.round(proxy.avg_response_ms)}ms` : '—'}
                    </td>
                    <td style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                      {proxy.last_checked_at ? new Date(proxy.last_checked_at).toLocaleString() : '—'}
                    </td>
                  </tr>
                ))}
                <tr ref={sentinelRef as any}>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '16px 0', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                    {loadingMore && <div className="spinner" style={{ margin: '0 auto' }} />}
                    {!loadingMore && proxies.length < proxyTotal && <span>Scroll to load more...</span>}
                    {!loadingMore && proxies.length >= proxyTotal && proxyTotal > 0 && <span>All proxies loaded</span>}
                  </td>
                </tr>
              </>
            )}
          </tbody>
        </table>
      </div>

      {/* Performance Matrix (from latest validation) */}
      {latestValidation && latestValidation.url_checks.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12 }}>
            Performance Matrix
          </h2>
          <div className="card table-card">
            <table>
              <thead>
                <tr>
                  <th>Validation URL</th>
                  <th>Tested</th>
                  <th>Passed</th>
                  <th>Failed</th>
                  <th>Pass Rate</th>
                  <th>Avg Response</th>
                </tr>
              </thead>
              <tbody>
                {latestValidation.url_checks.map((uc) => {
                  const rate = uc.proxies_tested > 0 ? Math.round(uc.proxies_passed / uc.proxies_tested * 100) : 0;
                  return (
                    <tr key={uc.id}>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', maxWidth: 400, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {uc.url}
                      </td>
                      <td>{uc.proxies_tested}</td>
                      <td style={{ color: 'var(--status-success)' }}>{uc.proxies_passed}</td>
                      <td style={{ color: 'var(--status-failed)' }}>{uc.proxies_failed}</td>
                      <td>
                        <span style={{
                          fontWeight: 600,
                          color: rate >= 80 ? 'var(--status-success)' : rate >= 50 ? 'var(--status-running)' : 'var(--status-failed)',
                        }}>
                          {rate}%
                        </span>
                      </td>
                      <td style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                        {uc.avg_response_ms != null ? `${Math.round(uc.avg_response_ms)}ms` : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Fetch Logs */}
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12 }}>
          Fetch History ({fetchLogsTotal})
        </h2>
        {fetchLogs.length === 0 ? (
          <div className="card" style={{ padding: 20, color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            No fetch history yet
          </div>
        ) : (
          <div className="card table-card">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Status</th>
                  <th>Found</th>
                  <th>New</th>
                  <th>Updated</th>
                  <th>Truncated</th>
                  <th>Duration</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {fetchLogs.map((log) => (
                  <tr key={log.id}>
                    <td style={{ fontSize: '0.82rem' }}>{new Date(log.created_at).toLocaleString()}</td>
                    <td>
                      <span className={`badge badge--${log.status === 'success' ? 'success' : 'failed'}`}>
                        {log.status}
                      </span>
                    </td>
                    <td>{log.proxies_found}</td>
                    <td style={{ color: 'var(--status-success)' }}>{log.proxies_new}</td>
                    <td>{log.proxies_updated}</td>
                    <td>{log.proxies_truncated > 0 ? log.proxies_truncated : '—'}</td>
                    <td style={{ fontSize: '0.82rem' }}>{Math.round(log.duration_ms)}ms</td>
                    <td style={{ fontSize: '0.78rem', color: 'var(--status-failed)', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {log.error_message || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Validation Logs */}
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 12 }}>
          Validation History ({validationLogsTotal})
        </h2>
        {validationLogs.length === 0 ? (
          <div className="card" style={{ padding: 20, color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            No validation history yet
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {validationLogs.map((log) => (
              <div key={log.id} className="card" style={{ padding: 20 }}>
                <div
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
                  onClick={() => setExpandedLog(expandedLog === log.id ? null : log.id)}
                >
                  <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
                    <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                      {new Date(log.created_at).toLocaleString()}
                    </span>
                    <span className={`badge badge--${log.status === 'success' ? 'success' : 'failed'}`}>
                      {log.status}
                    </span>
                    <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                      {log.proxies_tested} tested
                    </span>
                    <span style={{ fontSize: '0.82rem', color: 'var(--status-success)' }}>
                      {log.proxies_healthy} healthy
                    </span>
                    <span style={{ fontSize: '0.82rem', color: 'var(--status-running)' }}>
                      {log.proxies_degraded} degraded
                    </span>
                    <span style={{ fontSize: '0.82rem', color: 'var(--status-failed)' }}>
                      {log.proxies_unhealthy} unhealthy
                    </span>
                    {log.proxies_removed > 0 && (
                      <span style={{ fontSize: '0.82rem', color: 'var(--status-failed)' }}>
                        ({log.proxies_removed} removed)
                      </span>
                    )}
                  </div>
                  <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                    {Math.round(log.duration_ms / 1000)}s
                    {log.url_checks.length > 0 && (expandedLog === log.id ? ' ▲' : ' ▼')}
                  </span>
                </div>

                {/* Expanded: per-URL performance */}
                {expandedLog === log.id && log.url_checks.length > 0 && (
                  <table style={{ marginTop: 12 }}>
                    <thead>
                      <tr>
                        <th>URL</th>
                        <th>Tested</th>
                        <th>Passed</th>
                        <th>Failed</th>
                        <th>Pass Rate</th>
                        <th>Avg ms</th>
                      </tr>
                    </thead>
                    <tbody>
                      {log.url_checks.map((uc) => {
                        const rate = uc.proxies_tested > 0 ? Math.round(uc.proxies_passed / uc.proxies_tested * 100) : 0;
                        return (
                          <tr key={uc.id}>
                            <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', maxWidth: 400, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {uc.url}
                            </td>
                            <td>{uc.proxies_tested}</td>
                            <td style={{ color: 'var(--status-success)' }}>{uc.proxies_passed}</td>
                            <td style={{ color: 'var(--status-failed)' }}>{uc.proxies_failed}</td>
                            <td>
                              <span style={{
                                fontWeight: 600,
                                color: rate >= 80 ? 'var(--status-success)' : rate >= 50 ? 'var(--status-running)' : 'var(--status-failed)',
                              }}>
                                {rate}%
                              </span>
                            </td>
                            <td>{uc.avg_response_ms != null ? Math.round(uc.avg_response_ms) : '—'}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}

                {log.error_message && (
                  <div style={{ marginTop: 8, fontSize: '0.8rem', color: 'var(--status-failed)' }}>
                    {log.error_message}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <div className="card" style={{ padding: '16px 20px', textAlign: 'center' }}>
      <div style={{ fontSize: '1.5rem', fontWeight: 700, color: color || 'var(--text-primary)' }}>
        {value}
      </div>
      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 2 }}>
        {label}
      </div>
    </div>
  );
}