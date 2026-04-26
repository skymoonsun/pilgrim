import { Link } from 'react-router-dom';
import { proxySourceApi } from '../../api/client';
import type { ProxySourceConfig } from '../../api/client';
import { IconPlus, IconEye, IconEdit, IconTrash, IconGlobe, IconRefresh } from '../../components/icons/Icons';
import { useInfiniteScroll } from '../../hooks/useInfiniteScroll';
import { confirmDialog } from '../../components/ui/ConfirmDialog';
import { toast } from '../../components/ui/Toast';

export default function ProxySources() {
  const { items: sources, total, loading, loadingMore, sentinelRef, reset } = useInfiniteScroll<ProxySourceConfig>({
    fetchPage: (skip, limit) => proxySourceApi.list(skip, limit),
    pageSize: 50,
  });

  async function handleDelete(id: string, name: string) {
    if (!(await confirmDialog({ title: 'Delete Proxy Source', message: `Delete proxy source "${name}"?`, danger: true }))) return;
    try {
      await proxySourceApi.delete(id);
      reset();
    } catch (err) {
      toast.error(`Failed to delete: ${err instanceof Error ? err.message : err}`);
    }
  }

  async function handleFetch(id: string) {
    try {
      await proxySourceApi.triggerFetch(id);
      toast.success('Fetch task queued!');
    } catch (err) {
      toast.error(`Failed to trigger fetch: ${err instanceof Error ? err.message : err}`);
    }
  }

  if (loading && sources.length === 0) {
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
          <h1 className="page-title">Proxy Sources</h1>
          <p className="page-subtitle">{total} proxy source{total !== 1 ? 's' : ''} configured</p>
        </div>
        <Link to="/proxy-sources/new" className="btn btn-primary">
          <IconPlus size={16} /> New Source
        </Link>
      </div>

      <div className="card table-card">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Format</th>
              <th>Status</th>
              <th>Last Fetched</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {sources.length === 0 ? (
              <tr>
                <td colSpan={5}>
                  <div className="empty-state">
                    <div className="empty-state-icon"><IconGlobe size={48} /></div>
                    <div className="empty-state-text">No proxy sources yet</div>
                    <div className="empty-state-sub">
                      Add a proxy list source to start collecting proxies
                    </div>
                  </div>
                </td>
              </tr>
            ) : (
              <>
                {sources.map((source) => (
                  <tr key={source.id}>
                    <td>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                        {source.name}
                      </div>
                      {source.description && (
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 2 }}>
                          {source.description.slice(0, 80)}{source.description.length > 80 ? '…' : ''}
                        </div>
                      )}
                    </td>
                    <td>
                      <span className="badge badge--queued">{source.format_type}</span>
                    </td>
                    <td>
                      <span className={`badge badge--${source.is_active ? 'success' : 'cancelled'}`}>
                        {source.is_active ? 'Active' : 'Inactive'}
                      </span>
                      {source.last_fetch_error && (
                        <div style={{ fontSize: '0.7rem', color: 'var(--status-failed)', marginTop: 2 }}>
                          Error: {source.last_fetch_error.slice(0, 50)}
                        </div>
                      )}
                    </td>
                    <td>
                      {source.last_fetched_at
                        ? new Date(source.last_fetched_at).toLocaleString()
                        : '—'}
                    </td>
                    <td>
                      <div className="action-btns">
                        <Link to={`/proxy-sources/${source.id}`} className="action-btn" title="View">
                          <IconEye size={16} />
                        </Link>
                        <Link to={`/proxy-sources/${source.id}/edit`} className="action-btn" title="Edit">
                          <IconEdit size={16} />
                        </Link>
                        <button
                          type="button"
                          className="action-btn"
                          title="Fetch Now"
                          onClick={() => handleFetch(source.id)}
                        >
                          <IconRefresh size={16} />
                        </button>
                        <button
                          type="button"
                          className="action-btn action-btn--delete"
                          title="Delete"
                          onClick={() => handleDelete(source.id, source.name)}
                        >
                          <IconTrash size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                <tr ref={sentinelRef as any}>
                  <td colSpan={5} style={{ textAlign: 'center', padding: '16px 0', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                    {loadingMore && <div className="spinner" style={{ margin: '0 auto' }} />}
                    {!loadingMore && sources.length < total && <span>Scroll to load more...</span>}
                    {!loadingMore && sources.length >= total && total > 0 && <span>All proxy sources loaded</span>}
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