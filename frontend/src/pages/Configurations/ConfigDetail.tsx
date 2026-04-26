import { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { configsApi } from '../../api/client';
import type { CrawlConfig } from '../../api/client';
import { IconConfig, IconFlask, IconEdit, IconTrash, IconRefresh } from '../../components/icons/Icons';
import { confirmDialog } from '../../components/ui/ConfirmDialog';

export default function ConfigDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [config, setConfig] = useState<CrawlConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (id) loadConfig(id);
  }, [id]);

  async function loadConfig(configId: string) {
    setLoading(true);
    try {
      const res = await configsApi.get(configId);
      setConfig(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load config');
    }
    setLoading(false);
  }

  async function handleDelete() {
    if (!config || !(await confirmDialog({ title: 'Delete Configuration', message: `Delete "${config.name}"?`, danger: true }))) return;
    try {
      await configsApi.delete(config.id);
      navigate('/configurations');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    }
  }

  async function handleToggleActive() {
    if (!config) return;
    try {
      const updated = await configsApi.update(config.id, {
        is_active: !config.is_active,
      });
      setConfig(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Update failed');
    }
  }

  if (loading) {
    return (
      <div className="loading-overlay">
        <div className="spinner" />
      </div>
    );
  }

  if (error || !config) {
    return (
      <div className="animate-in">
        <div className="card" style={{ padding: 40, textAlign: 'center' }}>
          <div className="empty-state-icon"><IconConfig size={48} /></div>
          <div className="empty-state-text">{error || 'Config not found'}</div>
          <Link to="/configurations" className="btn btn-secondary" style={{ marginTop: 16 }}>
            ← Back to Configurations
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">{config.name}</h1>
          <p className="page-subtitle">
            {config.description || 'No description'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <Link to={`/configurations/${config.id}/edit`} className="btn btn-primary">
            <IconEdit size={16} /> Edit
          </Link>
          <Link to={`/scrape?config=${config.id}`} className="btn btn-secondary">
            <IconFlask size={16} /> Test Scrape
          </Link>
          <button className="btn btn-secondary" onClick={handleToggleActive}>
            <IconRefresh size={16} />
            {config.is_active ? 'Deactivate' : 'Activate'}
          </button>
          <button className="btn btn-secondary" onClick={handleDelete}
            style={{ borderColor: 'var(--status-failed)', color: 'var(--status-failed)' }}>
            <IconTrash size={16} /> Delete
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        {/* General Info */}
        <div className="card" style={{ padding: 28 }}>
          <h3 className="card-title" style={{ marginBottom: 20 }}>General</h3>
          <div className="detail-grid">
            <DetailRow label="ID" value={config.id} mono />
            <DetailRow label="Status" value={
              <span className={`badge badge--${config.is_active ? 'success' : 'cancelled'}`}>
                {config.is_active ? 'Active' : 'Inactive'}
              </span>
            } />
            <DetailRow label="Profile" value={
              <span className="badge badge--queued">{config.scraper_profile}</span>
            } />
            <DetailRow label="Proxy" value={config.use_proxy ? 'Enabled' : 'Disabled'} />
            <DetailRow label="Rotate UA" value={config.rotate_user_agent ? 'Yes' : 'No'} />
            <DetailRow label="Custom Delay" value={config.custom_delay ? `${config.custom_delay}s` : '—'} />
            <DetailRow label="Max Concurrent" value={config.max_concurrent?.toString() || '—'} />
            <DetailRow label="Sanitizer" value={config.sanitizer_config ? config.sanitizer_config.name : '—'} />
            <DetailRow label="Created" value={new Date(config.created_at).toLocaleString()} />
            <DetailRow label="Updated" value={new Date(config.updated_at).toLocaleString()} />
          </div>
        </div>

        {/* Extraction Spec */}
        <div className="card" style={{ padding: 28 }}>
          <h3 className="card-title" style={{ marginBottom: 20 }}>Extraction Spec</h3>
          <pre style={{
            background: 'var(--bg-tertiary)',
            borderRadius: 'var(--radius-md)',
            padding: 18,
            fontSize: '0.78rem',
            fontFamily: 'var(--font-mono)',
            color: 'var(--text-secondary)',
            overflow: 'auto',
            maxHeight: 400,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            margin: 0,
          }}>
            {JSON.stringify(config.extraction_spec, null, 2)}
          </pre>
        </div>

        {/* Fetch Options */}
        <div className="card" style={{ padding: 28 }}>
          <h3 className="card-title" style={{ marginBottom: 20 }}>Fetch Options</h3>
          {config.fetch_options ? (
            <pre style={{
              background: 'var(--bg-tertiary)',
              borderRadius: 'var(--radius-md)',
              padding: 18,
              fontSize: '0.78rem',
              fontFamily: 'var(--font-mono)',
              color: 'var(--text-secondary)',
              overflow: 'auto',
              maxHeight: 300,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              margin: 0,
            }}>
              {JSON.stringify(config.fetch_options, null, 2)}
            </pre>
          ) : (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              No custom fetch options configured
            </p>
          )}
        </div>

        {/* Custom Headers */}
        <div className="card" style={{ padding: 28 }}>
          <h3 className="card-title" style={{ marginBottom: 20 }}>Custom Headers</h3>
          {config.custom_headers ? (
            <pre style={{
              background: 'var(--bg-tertiary)',
              borderRadius: 'var(--radius-md)',
              padding: 18,
              fontSize: '0.78rem',
              fontFamily: 'var(--font-mono)',
              color: 'var(--text-secondary)',
              overflow: 'auto',
              maxHeight: 300,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              margin: 0,
            }}>
              {JSON.stringify(config.custom_headers, null, 2)}
            </pre>
          ) : (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              No custom headers configured
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function DetailRow({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: '10px 0',
      borderBottom: '1px solid var(--border-subtle)',
    }}>
      <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>{label}</span>
      <span style={{
        color: 'var(--text-primary)',
        fontSize: mono ? '0.78rem' : '0.85rem',
        fontFamily: mono ? 'var(--font-mono)' : 'inherit',
        maxWidth: '60%',
        textAlign: 'right',
        wordBreak: 'break-all',
      }}>
        {value}
      </span>
    </div>
  );
}
