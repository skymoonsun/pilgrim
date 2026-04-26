import { useState } from 'react';
import { Link } from 'react-router-dom';
import { sanitizerConfigsApi } from '../../api/client';
import type { SanitizerConfig } from '../../api/client';
import { IconPlus, IconRefresh, IconFilter, IconEye, IconEdit, IconTrash } from '../../components/icons/Icons';
import { useInfiniteScroll } from '../../hooks/useInfiniteScroll';
import { confirmDialog } from '../../components/ui/ConfirmDialog';

export default function SanitizerConfigs() {
  const [activeOnly, setActiveOnly] = useState(false);

  const { items: configs, total, loading, loadingMore, sentinelRef, reset } = useInfiniteScroll<SanitizerConfig>({
    fetchPage: (skip, limit) =>
      sanitizerConfigsApi.list(skip, limit, activeOnly),
    pageSize: 50,
    deps: [activeOnly],
  });

  async function handleDelete(id: string, e: React.MouseEvent) {
    e.preventDefault();
    if (!(await confirmDialog({ title: 'Delete Sanitizer Config', message: 'Delete this sanitizer config?', danger: true }))) return;
    await sanitizerConfigsApi.delete(id);
    reset();
  }

  if (loading && configs.length === 0) {
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
          <h1 className="page-title">Sanitizer Configs</h1>
          <p className="page-subtitle">{total} config{total !== 1 ? 's' : ''}</p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button
            className={`btn ${activeOnly ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setActiveOnly(!activeOnly)}
            style={{ padding: '4px 12px', fontSize: '0.8rem' }}
          >
            <IconFilter size={14} /> {activeOnly ? 'Active Only' : 'All'}
          </button>
          <Link to="/sanitizer-configs/new" className="btn btn-primary">
            <IconPlus size={16} /> New Sanitizer
          </Link>
          <button className="btn btn-secondary" onClick={reset}>
            <IconRefresh size={16} />
          </button>
        </div>
      </div>

      <div className="card table-card">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Description</th>
              <th>Rules</th>
              <th>Status</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {configs.length === 0 ? (
              <tr>
                <td colSpan={6}>
                  <div className="empty-state">
                    <div className="empty-state-icon"><IconFilter size={48} /></div>
                    <div className="empty-state-text">No sanitizer configs found</div>
                    <div className="empty-state-sub">
                      Create a sanitizer config to transform extracted data
                    </div>
                  </div>
                </td>
              </tr>
            ) : (
              <>
                {configs.map((config) => (
                  <tr key={config.id}>
                    <td style={{ fontWeight: 600 }}>{config.name}</td>
                    <td style={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {config.description || '—'}
                    </td>
                    <td>
                      <span className="badge badge--running">
                        {config.rules.length} rule{config.rules.length !== 1 ? 's' : ''}
                      </span>
                    </td>
                    <td>
                      <span className={`badge badge--${config.is_active ? 'success' : 'cancelled'}`}>
                        {config.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td>{new Date(config.created_at).toLocaleDateString()}</td>
                    <td>
                      <div className="action-btns">
                        <Link to={`/sanitizer-configs/${config.id}`} className="action-btn" title="View Details">
                          <IconEye size={16} />
                        </Link>
                        <Link to={`/sanitizer-configs/${config.id}/edit`} className="action-btn" title="Edit">
                          <IconEdit size={16} />
                        </Link>
                        <button className="action-btn action-btn--danger" title="Delete" onClick={(e) => handleDelete(config.id, e)}>
                          <IconTrash size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                <tr ref={sentinelRef as any}>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '16px 0', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                    {loadingMore && <div className="spinner" style={{ margin: '0 auto' }} />}
                    {!loadingMore && configs.length < total && <span>Scroll to load more...</span>}
                    {!loadingMore && configs.length >= total && total > 0 && <span>All configs loaded</span>}
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