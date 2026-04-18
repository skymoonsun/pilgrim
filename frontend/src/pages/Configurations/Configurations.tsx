import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { configsApi } from '../../api/client';
import type { CrawlConfig } from '../../api/client';
import { IconPlus, IconEye, IconEdit, IconFlask, IconTrash, IconConfig } from '../../components/icons/Icons';

export default function Configurations() {
  const [configs, setConfigs] = useState<CrawlConfig[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadConfigs();
  }, []);

  async function loadConfigs() {
    setLoading(true);
    try {
      const res = await configsApi.list(0, 100);
      setConfigs(res.items);
      setTotal(res.total);
    } catch (err) {
      console.error('Failed to load configs:', err);
    }
    setLoading(false);
  }

  async function handleDelete(id: string, name: string) {
    if (!confirm(`Delete config "${name}"?`)) return;
    try {
      console.log('Deleting config:', id);
      await configsApi.delete(id);
      console.log('Delete succeeded');
      setConfigs((prev) => prev.filter((c) => c.id !== id));
      setTotal((prev) => prev - 1);
    } catch (err) {
      console.error('Delete failed:', err);
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
          <h1 className="page-title">Configurations</h1>
          <p className="page-subtitle">{total} crawl config{total !== 1 ? 's' : ''} registered</p>
        </div>
        <Link to="/configurations/new" className="btn btn-primary">
          <IconPlus size={16} /> New Config
        </Link>
      </div>

      <div className="card table-card">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Profile</th>
              <th>Status</th>
              <th>Proxy</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {configs.length === 0 ? (
              <tr>
                <td colSpan={6}>
                  <div className="empty-state">
                    <div className="empty-state-icon"><IconConfig size={48} /></div>
                    <div className="empty-state-text">No configurations yet</div>
                    <div className="empty-state-sub">
                      Create your first crawl config to get started
                    </div>
                  </div>
                </td>
              </tr>
            ) : (
              configs.map((config) => (
                <tr key={config.id}>
                  <td>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                      {config.name}
                    </div>
                    {config.description && (
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 2 }}>
                        {config.description.slice(0, 80)}
                        {config.description.length > 80 ? '…' : ''}
                      </div>
                    )}
                  </td>
                  <td>
                    <span className="badge badge--queued">{config.scraper_profile}</span>
                  </td>
                  <td>
                    <span className={`badge badge--${config.is_active ? 'success' : 'cancelled'}`}>
                      {config.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td>{config.use_proxy ? '✓' : '—'}</td>
                  <td>{new Date(config.created_at).toLocaleDateString()}</td>
                  <td>
                    <div className="action-btns">
                      <Link to={`/configurations/${config.id}`} className="action-btn" title="View">
                        <IconEye size={16} />
                      </Link>
                      <Link to={`/configurations/${config.id}/edit`} className="action-btn" title="Edit">
                        <IconEdit size={16} />
                      </Link>
                      <Link to={`/scrape?config=${config.id}`} className="action-btn" title="Test Scrape">
                        <IconFlask size={16} />
                      </Link>
                      <button
                        type="button"
                        className="action-btn action-btn--delete"
                        title="Delete"
                        onClick={(e) => {
                          e.stopPropagation();
                          e.preventDefault();
                          handleDelete(config.id, config.name);
                        }}
                      >
                        <IconTrash size={16} />
                      </button>
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
