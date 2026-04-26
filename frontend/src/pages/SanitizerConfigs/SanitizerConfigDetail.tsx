import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { sanitizerConfigsApi } from '../../api/client';
import type { SanitizerConfig } from '../../api/client';
import { IconEdit } from '../../components/icons/Icons';

const TRANSFORM_LABELS: Record<string, string> = {
  strip: 'Strip whitespace',
  to_lower: 'Lowercase',
  to_upper: 'Uppercase',
  to_number: 'To number',
  to_int: 'To integer',
  regex_replace: 'Regex replace',
  extract_number: 'Extract number',
  trim_prefix: 'Trim prefix',
  trim_suffix: 'Trim suffix',
  default: 'Default value',
  split_take: 'Split & take',
};

export default function SanitizerConfigDetail() {
  const { id } = useParams<{ id: string }>();
  const [config, setConfig] = useState<SanitizerConfig | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    sanitizerConfigsApi.get(id).then(setConfig).finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="loading-overlay"><div className="spinner" /></div>;
  if (!config) return <div className="animate-in"><p>Sanitizer config not found.</p></div>;

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">{config.name}</h1>
          <p className="page-subtitle">{config.description || 'No description'}</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Link to={`/sanitizer-configs/${config.id}/edit`} className="btn btn-primary">
            <IconEdit size={16} /> Edit
          </Link>
        </div>
      </div>

      <div className="card" style={{ padding: 28, marginBottom: 24 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div>
            <div className="detail-label">Status</div>
            <span className={`badge badge--${config.is_active ? 'success' : 'cancelled'}`}>
              {config.is_active ? 'Active' : 'Inactive'}
            </span>
          </div>
          <div>
            <div className="detail-label">Created</div>
            <div>{new Date(config.created_at).toLocaleString()}</div>
          </div>
          <div>
            <div className="detail-label">Updated</div>
            <div>{new Date(config.updated_at).toLocaleString()}</div>
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: 28 }}>
        <h3 className="card-title">Rules ({config.rules.length})</h3>
        {config.rules.length === 0 ? (
          <p style={{ color: 'var(--text-muted)' }}>No rules defined.</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: 16 }}>
            {config.rules.map((rule, idx) => (
              <div key={idx} style={{ padding: 16, border: '1px solid var(--border-color)', borderRadius: 8 }}>
                <div style={{ fontWeight: 600, marginBottom: 8, color: 'var(--accent-primary)' }}>
                  Field: {rule.field}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {rule.transforms.map((t, tIdx) => (
                    <div key={tIdx} style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                      <span style={{ fontWeight: 500 }}>{TRANSFORM_LABELS[t.type] || t.type}</span>
                      {t.type === 'regex_replace' && <span> — pattern: <code>{t.pattern}</code> → <code>{t.replacement || '(empty)'}</code></span>}
                      {t.type === 'trim_prefix' && <span> — remove prefix: <code>{t.value}</code></span>}
                      {t.type === 'trim_suffix' && <span> — remove suffix: <code>{t.value}</code></span>}
                      {t.type === 'default' && <span> — default: <code>{t.value}</code></span>}
                      {t.type === 'split_take' && <span> — split by <code>{t.pattern}</code>, take index {t.index ?? 0}</span>}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}