import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { schedulesApi, configsApi } from '../../api/client';
import type { CrawlConfig, Schedule } from '../../api/client';
import { IconPlus, IconTrash, IconCalendar, IconMail } from '../../components/icons/Icons';

interface ConfigEntry {
  config_link_id: string | null; // null = newly added
  config_id: string;
  urls: { id: string | null; url: string; label: string }[];
}

export default function ScheduleEdit() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [allConfigs, setAllConfigs] = useState<CrawlConfig[]>([]);

  const [form, setForm] = useState({
    name: '',
    description: '',
    timezone: 'UTC',
    scheduleType: 'interval' as 'interval' | 'cron',
    cron_expression: '',
    interval_minutes: '60',
    default_queue: 'crawl_default',
    is_active: true,
    configEntries: [] as ConfigEntry[],
    enableCallback: false,
    callbackUrl: '',
    callbackMethod: 'POST',
    callbackHeaders: '',
    callbackFieldMapping: '{}',
    callbackBatchResults: true,
    callbackRetryCount: '3',
    enableEmailNotification: false,
    emailRecipients: '',
    emailSubjectTemplate: 'Pilgrim: {{schedule_name}} completed',
    emailFieldMapping: '{}',
    emailOnSuccess: true,
    emailOnFailure: true,
    emailBatchResults: true,
    emailIncludeMetadata: true,
  });

  useEffect(() => {
    Promise.all([
      configsApi.list(0, 100),
      id ? schedulesApi.get(id) : Promise.resolve(null),
    ]).then(([configsRes, schedule]) => {
      setAllConfigs(configsRes.items);
      if (schedule) populateForm(schedule);
      setLoading(false);
    }).catch((err) => {
      setError(err instanceof Error ? err.message : 'Failed to load');
      setLoading(false);
    });
  }, [id]);

  function populateForm(s: Schedule) {
    const entries: ConfigEntry[] = s.config_links.map((cl) => ({
      config_link_id: cl.id,
      config_id: cl.config_id,
      urls: cl.url_targets.map((t) => ({
        id: t.id,
        url: t.url,
        label: t.label || '',
      })),
    }));

    setForm({
      name: s.name,
      description: s.description || '',
      timezone: s.timezone,
      scheduleType: s.cron_expression ? 'cron' : 'interval',
      cron_expression: s.cron_expression || '',
      interval_minutes: s.interval_seconds ? (s.interval_seconds / 60).toString() : '60',
      default_queue: s.default_queue,
      is_active: s.is_active,
      configEntries: entries,
      enableCallback: !!s.callback,
      callbackUrl: s.callback?.url || '',
      callbackMethod: s.callback?.method || 'POST',
      callbackHeaders: s.callback?.headers ? JSON.stringify(s.callback.headers, null, 2) : '',
      callbackFieldMapping: s.callback?.field_mapping ? JSON.stringify(s.callback.field_mapping, null, 2) : '{}',
      callbackBatchResults: s.callback?.batch_results ?? true,
      callbackRetryCount: s.callback?.retry_count?.toString() || '3',
      enableEmailNotification: !!s.email_notification,
      emailRecipients: s.email_notification?.recipient_emails?.join(', ') || '',
      emailSubjectTemplate: s.email_notification?.subject_template || 'Pilgrim: {{schedule_name}} completed',
      emailFieldMapping: s.email_notification?.field_mapping ? JSON.stringify(s.email_notification.field_mapping, null, 2) : '{}',
      emailOnSuccess: s.email_notification?.on_success ?? true,
      emailOnFailure: s.email_notification?.on_failure ?? true,
      emailBatchResults: s.email_notification?.batch_results ?? true,
      emailIncludeMetadata: s.email_notification?.include_metadata ?? true,
    });
  }

  function updateField(field: string, value: unknown) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  // ── Config entry management ───────────────────────────────────

  function addConfigEntry(configId: string) {
    setForm((prev) => ({
      ...prev,
      configEntries: [
        ...prev.configEntries,
        { config_link_id: null, config_id: configId, urls: [{ id: null, url: '', label: '' }] },
      ],
    }));
  }

  function removeConfigEntry(index: number) {
    setForm((prev) => ({
      ...prev,
      configEntries: prev.configEntries.filter((_, i) => i !== index),
    }));
  }

  function addUrlToConfig(configIndex: number) {
    setForm((prev) => {
      const entries = [...prev.configEntries];
      entries[configIndex] = {
        ...entries[configIndex],
        urls: [...entries[configIndex].urls, { id: null, url: '', label: '' }],
      };
      return { ...prev, configEntries: entries };
    });
  }

  function removeUrlFromConfig(configIndex: number, urlIndex: number) {
    setForm((prev) => {
      const entries = [...prev.configEntries];
      entries[configIndex] = {
        ...entries[configIndex],
        urls: entries[configIndex].urls.filter((_, i) => i !== urlIndex),
      };
      return { ...prev, configEntries: entries };
    });
  }

  function updateUrlInConfig(configIndex: number, urlIndex: number, field: 'url' | 'label', value: string) {
    setForm((prev) => {
      const entries = [...prev.configEntries];
      const urls = [...entries[configIndex].urls];
      urls[urlIndex] = { ...urls[urlIndex], [field]: value };
      entries[configIndex] = { ...entries[configIndex], urls };
      return { ...prev, configEntries: entries };
    });
  }

  const selectedConfigIds = form.configEntries.map((e) => e.config_id);
  const availableConfigs = allConfigs.filter((c) => !selectedConfigIds.includes(c.id));

  function getConfigName(configId: string) {
    return allConfigs.find((c) => c.id === configId)?.name || configId.slice(0, 8);
  }

  // ── Submit ────────────────────────────────────────────────────
  // Strategy: delete & recreate the schedule with updated data.
  // This is simpler than diffing config_links and URL targets individually.

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!id) return;
    setError('');
    setSaving(true);

    try {
      // 1. Update basic fields
      const updateData: Record<string, unknown> = {
        name: form.name,
        description: form.description || null,
        timezone: form.timezone,
        default_queue: form.default_queue,
        is_active: form.is_active,
      };

      if (form.scheduleType === 'cron') {
        updateData.cron_expression = form.cron_expression;
        updateData.interval_seconds = null;
      } else {
        updateData.interval_seconds = parseInt(form.interval_minutes) * 60;
        updateData.cron_expression = null;
      }

      await schedulesApi.update(id, updateData as Partial<Schedule>);

      // 2. Delete the old schedule and recreate (simpler than diff)
      // Actually, let's do it properly: delete + create
      await schedulesApi.delete(id);

      const config_links = form.configEntries
        .filter((entry) => entry.urls.some((u) => u.url.trim()))
        .map((entry) => ({
          config_id: entry.config_id,
          urls: entry.urls
            .filter((u) => u.url.trim())
            .map((u) => ({ url: u.url, label: u.label || null })),
        }));

      let callback = undefined;
      if (form.enableCallback && form.callbackUrl) {
        let field_mapping = {};
        try { field_mapping = JSON.parse(form.callbackFieldMapping || '{}'); }
        catch { setError('Invalid JSON in field mapping'); setSaving(false); return; }

        let headers = null;
        if (form.callbackHeaders.trim()) {
          try { headers = JSON.parse(form.callbackHeaders); }
          catch { setError('Invalid JSON in callback headers'); setSaving(false); return; }
        }

        callback = {
          url: form.callbackUrl,
          method: form.callbackMethod,
          headers,
          field_mapping,
          batch_results: form.callbackBatchResults,
          retry_count: parseInt(form.callbackRetryCount),
        };
      }

      let email_notification = undefined;
      if (form.enableEmailNotification && form.emailRecipients.trim()) {
        let email_field_mapping = {};
        try { email_field_mapping = JSON.parse(form.emailFieldMapping || '{}'); }
        catch { setError('Invalid JSON in email field mapping'); setSaving(false); return; }

        email_notification = {
          recipient_emails: form.emailRecipients.split(',').map((e: string) => e.trim()).filter((e: string) => e),
          subject_template: form.emailSubjectTemplate,
          field_mapping: email_field_mapping,
          include_metadata: form.emailIncludeMetadata,
          batch_results: form.emailBatchResults,
          on_success: form.emailOnSuccess,
          on_failure: form.emailOnFailure,
        };
      }

      const created = await schedulesApi.create({
        name: form.name,
        description: form.description || null,
        timezone: form.timezone,
        default_queue: form.default_queue,
        cron_expression: form.scheduleType === 'cron' ? form.cron_expression : null,
        interval_seconds: form.scheduleType === 'interval' ? parseInt(form.interval_minutes) * 60 : null,
        config_links,
        callback,
        email_notification,
      });

      navigate(`/schedules/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Update failed');
    }
    setSaving(false);
  }

  if (loading) {
    return <div className="loading-overlay"><div className="spinner" /></div>;
  }

  if (error && !form.name) {
    return (
      <div className="animate-in">
        <div className="card" style={{ padding: 40, textAlign: 'center' }}>
          <div className="empty-state-icon"><IconCalendar size={48} /></div>
          <div className="empty-state-text">{error}</div>
          <Link to="/schedules" className="btn btn-secondary" style={{ marginTop: 16 }}>← Back</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">Edit: {form.name}</h1>
          <p className="page-subtitle">Modify schedule settings, configs, and URLs</p>
        </div>
      </div>

      {error && (
        <div style={{
          background: 'var(--status-failed-bg)',
          border: '1px solid rgba(255,82,82,0.3)',
          borderRadius: 'var(--radius-md)',
          padding: '14px 18px',
          color: 'var(--status-failed)',
          fontSize: '0.85rem',
          marginBottom: 20,
        }}>
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>

          {/* ── Left column ── */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            <div className="card" style={{ padding: 28 }}>
              <h3 className="card-title" style={{ marginBottom: 20 }}>General</h3>
              <div className="form-group">
                <label className="form-label">Name *</label>
                <input type="text" className="form-input" value={form.name}
                  onChange={(e) => updateField('name', e.target.value)} required maxLength={200} />
              </div>
              <div className="form-group">
                <label className="form-label">Description</label>
                <textarea className="form-input" value={form.description}
                  onChange={(e) => updateField('description', e.target.value)}
                  rows={2} style={{ resize: 'vertical' }} />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <div className="form-group">
                  <label className="form-label">Timezone</label>
                  <input type="text" className="form-input" value={form.timezone}
                    onChange={(e) => updateField('timezone', e.target.value)} />
                </div>
                <div className="form-group">
                  <label className="form-label">Queue</label>
                  <select className="form-input form-select" value={form.default_queue}
                    onChange={(e) => updateField('default_queue', e.target.value)}>
                    <option value="crawl_high">crawl_high</option>
                    <option value="crawl_default">crawl_default</option>
                    <option value="crawl_low">crawl_low</option>
                  </select>
                </div>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer', marginTop: 8 }}>
                <input type="checkbox" checked={form.is_active}
                  onChange={(e) => updateField('is_active', e.target.checked)} />
                Active
              </label>
            </div>

            <div className="card" style={{ padding: 28 }}>
              <h3 className="card-title" style={{ marginBottom: 20 }}>Schedule Timing</h3>
              <div className="form-group">
                <label className="form-label">Type</label>
                <div style={{ display: 'flex', gap: 12 }}>
                  {(['interval', 'cron'] as const).map((type) => (
                    <button type="button" key={type}
                      className={`btn ${form.scheduleType === type ? 'btn-primary' : 'btn-secondary'}`}
                      onClick={() => updateField('scheduleType', type)}
                      style={{ flex: 1, justifyContent: 'center' }}>
                      {type === 'interval' ? 'Interval' : 'Cron Expression'}
                    </button>
                  ))}
                </div>
              </div>
              {form.scheduleType === 'interval' ? (
                <div className="form-group">
                  <label className="form-label">Interval (minutes)</label>
                  <input type="number" className="form-input" min="1" value={form.interval_minutes}
                    onChange={(e) => updateField('interval_minutes', e.target.value)} />
                </div>
              ) : (
                <div className="form-group">
                  <label className="form-label">Cron Expression</label>
                  <input type="text" className="form-input" placeholder="0 */6 * * *"
                    value={form.cron_expression}
                    onChange={(e) => updateField('cron_expression', e.target.value)} />
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 4 }}>
                    min hour day month weekday
                  </div>
                </div>
              )}
            </div>

            {/* Callback */}
            <div className="card" style={{ padding: 28 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <h3 className="card-title" style={{ margin: 0 }}>Callback</h3>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
                  <input type="checkbox" checked={form.enableCallback}
                    onChange={(e) => updateField('enableCallback', e.target.checked)} />
                  Enable
                </label>
              </div>
              {form.enableCallback && (
                <>
                  <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
                    <div className="form-group">
                      <label className="form-label">Webhook URL</label>
                      <input type="url" className="form-input" value={form.callbackUrl}
                        onChange={(e) => updateField('callbackUrl', e.target.value)} />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Method</label>
                      <select className="form-input form-select" value={form.callbackMethod}
                        onChange={(e) => updateField('callbackMethod', e.target.value)}>
                        <option>POST</option><option>PUT</option><option>PATCH</option>
                      </select>
                    </div>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Headers (JSON)</label>
                    <textarea className="form-input" rows={2} value={form.callbackHeaders}
                      onChange={(e) => updateField('callbackHeaders', e.target.value)}
                      style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem' }} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Field Mapping (JSON)</label>
                    <textarea className="form-input" rows={5} value={form.callbackFieldMapping}
                      onChange={(e) => updateField('callbackFieldMapping', e.target.value)}
                      style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', whiteSpace: 'pre' }} />
                  </div>
                  <div style={{ display: 'flex', gap: 16, alignItems: 'end' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
                      <input type="checkbox" checked={form.callbackBatchResults}
                        onChange={(e) => updateField('callbackBatchResults', e.target.checked)} />
                      Batch Results
                    </label>
                    <div className="form-group" style={{ flex: 0 }}>
                      <label className="form-label" style={{ fontSize: '0.75rem' }}>Retries</label>
                      <input type="number" className="form-input" min="0" max="10" style={{ width: 70 }}
                        value={form.callbackRetryCount}
                        onChange={(e) => updateField('callbackRetryCount', e.target.value)} />
                    </div>
                  </div>
                </>
              )}
            </div>

            {/* Email Notification */}
            <div className="card" style={{ padding: 28 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                <h3 className="card-title" style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <IconMail size={18} /> Email Notification
                </h3>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
                  <input type="checkbox" checked={form.enableEmailNotification}
                    onChange={(e) => updateField('enableEmailNotification', e.target.checked)} />
                  Enable
                </label>
              </div>
              {form.enableEmailNotification && (
                <>
                  <div className="form-group">
                    <label className="form-label">Recipients (comma-separated)</label>
                    <input type="text" className="form-input" placeholder="user@example.com, admin@example.com"
                      value={form.emailRecipients}
                      onChange={(e) => updateField('emailRecipients', e.target.value)} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Subject Template</label>
                    <input type="text" className="form-input" value={form.emailSubjectTemplate}
                      onChange={(e) => updateField('emailSubjectTemplate', e.target.value)} />
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 4 }}>
                      Use {'{{schedule_name}}'}, {'{{job_id}}'}, etc. as placeholders
                    </div>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Field Mapping (JSON)</label>
                    <textarea className="form-input" rows={4} value={form.emailFieldMapping}
                      onChange={(e) => updateField('emailFieldMapping', e.target.value)}
                      style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', whiteSpace: 'pre' }} />
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 4 }}>
                      Use $.data.*, $.url, $.metadata.* paths (same as callback)
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
                      <input type="checkbox" checked={form.emailOnSuccess}
                        onChange={(e) => updateField('emailOnSuccess', e.target.checked)} />
                      On Success
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
                      <input type="checkbox" checked={form.emailOnFailure}
                        onChange={(e) => updateField('emailOnFailure', e.target.checked)} />
                      On Failure
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
                      <input type="checkbox" checked={form.emailBatchResults}
                        onChange={(e) => updateField('emailBatchResults', e.target.checked)} />
                      Batch Results
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-secondary)', fontSize: '0.85rem', cursor: 'pointer' }}>
                      <input type="checkbox" checked={form.emailIncludeMetadata}
                        onChange={(e) => updateField('emailIncludeMetadata', e.target.checked)} />
                      Include Metadata
                    </label>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* ── Right: Config + URL pairs ── */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            {availableConfigs.length > 0 && (
              <div className="card" style={{ padding: 28 }}>
                <h3 className="card-title" style={{ marginBottom: 16 }}>Add Config + URLs</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {availableConfigs.map((config) => (
                    <button type="button" key={config.id} onClick={() => addConfigEntry(config.id)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: '10px 14px', background: 'var(--bg-tertiary)',
                        border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)',
                        cursor: 'pointer', color: 'var(--text-primary)', width: '100%', textAlign: 'left',
                      }}>
                      <IconPlus size={14} />
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 600, fontSize: '0.85rem' }}>{config.name}</div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{config.scraper_profile}</div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {form.configEntries.map((entry, ci) => (
              <div key={`${entry.config_id}-${ci}`} className="card" style={{
                padding: 28, border: '1px solid var(--accent-cyan)',
                boxShadow: '0 0 12px rgba(0,240,255,0.06)',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                  <h3 className="card-title" style={{ margin: 0 }}>
                    <span style={{ color: 'var(--accent-cyan)' }}>{getConfigName(entry.config_id)}</span>
                  </h3>
                  <button type="button" className="action-btn" onClick={() => removeConfigEntry(ci)}
                    style={{ color: 'var(--status-failed)' }}>
                    <IconTrash size={16} />
                  </button>
                </div>
                <label className="form-label">Target URLs</label>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {entry.urls.map((urlItem, ui) => (
                    <div key={ui} style={{ display: 'flex', gap: 8, alignItems: 'start' }}>
                      <div style={{ flex: 1 }}>
                        <input type="url" className="form-input" placeholder="https://example.com/page"
                          value={urlItem.url} onChange={(e) => updateUrlInConfig(ci, ui, 'url', e.target.value)}
                          style={{ marginBottom: 4 }} />
                        <input type="text" className="form-input" placeholder="Label (optional)"
                          value={urlItem.label} onChange={(e) => updateUrlInConfig(ci, ui, 'label', e.target.value)}
                          style={{ fontSize: '0.8rem' }} />
                      </div>
                      {entry.urls.length > 1 && (
                        <button type="button" className="action-btn" onClick={() => removeUrlFromConfig(ci, ui)}
                          style={{ marginTop: 6 }}><IconTrash size={14} /></button>
                      )}
                    </div>
                  ))}
                </div>
                <button type="button" className="btn btn-secondary" onClick={() => addUrlToConfig(ci)}
                  style={{ marginTop: 10 }}>
                  <IconPlus size={14} /> Add URL
                </button>
              </div>
            ))}

            {form.configEntries.length === 0 && (
              <div className="card" style={{ padding: 40, textAlign: 'center' }}>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                  Select configs from the list above to add URL targets
                </div>
              </div>
            )}
          </div>
        </div>

        <div style={{ marginTop: 24, display: 'flex', gap: 12 }}>
          <button type="submit" className="btn btn-primary"
            disabled={saving || !form.name || form.configEntries.length === 0}
            style={{ minWidth: 180, justifyContent: 'center' }}>
            {saving ? <><div className="spinner" /> Saving...</> : 'Save Changes'}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => navigate(`/schedules/${id}`)}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
