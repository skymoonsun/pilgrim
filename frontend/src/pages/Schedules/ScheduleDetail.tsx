import { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { schedulesApi } from '../../api/client';
import type { Schedule, CallbackLog, EmailNotificationLog } from '../../api/client';
import {
  IconCalendar, IconClock, IconPlay, IconTrash, IconPause,
  IconPlus, IconLink, IconWebhook, IconRefresh, IconEdit, IconMail, IconGlobe,
} from '../../components/icons/Icons';
import { confirmDialog } from '../../components/ui/ConfirmDialog';
import { toast } from '../../components/ui/Toast';

export default function ScheduleDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [schedule, setSchedule] = useState<Schedule | null>(null);
  const [logs, setLogs] = useState<CallbackLog[]>([]);
  const [emailLogs, setEmailLogs] = useState<EmailNotificationLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Per-config-link URL add form state
  const [newUrls, setNewUrls] = useState<Record<string, { url: string; label: string }>>({});

  useEffect(() => {
    if (id) loadSchedule(id);
  }, [id]);

  async function loadSchedule(scheduleId: string) {
    setLoading(true);
    try {
      const res = await schedulesApi.get(scheduleId);
      setSchedule(res);
      if (res.callback) {
        const logsRes = await schedulesApi.getCallbackLogs(scheduleId, 0, 20);
        setLogs(logsRes);
      }
      if (res.email_notification) {
        const emailLogsRes = await schedulesApi.getEmailNotificationLogs(scheduleId, 0, 20);
        setEmailLogs(emailLogsRes);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load');
    }
    setLoading(false);
  }

  async function handleTrigger() {
    if (!schedule || !(await confirmDialog({ title: 'Trigger Schedule', message: 'Trigger this schedule now?' }))) return;
    try {
      const res = await schedulesApi.trigger(schedule.id);
      if (res.schedule_type === 'proxy_source') {
        toast.success(`${res.fetches_triggered} proxy source fetches triggered!`);
      } else {
        toast.info(`${res.jobs_created} jobs created!`);
      }
      loadSchedule(schedule.id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Trigger failed');
    }
  }

  async function handleToggle() {
    if (!schedule) return;
    try {
      await schedulesApi.update(schedule.id, { is_active: !schedule.is_active } as Partial<Schedule>);
      loadSchedule(schedule.id);
    } catch (err) {
      console.error(err);
    }
  }

  async function handleDelete() {
    if (!schedule || !(await confirmDialog({ title: 'Delete Schedule', message: `Delete "${schedule.name}"?`, danger: true }))) return;
    try {
      await schedulesApi.delete(schedule.id);
      navigate('/schedules');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Delete failed');
    }
  }

  async function handleAddUrl(configLinkId: string) {
    if (!schedule) return;
    const data = newUrls[configLinkId];
    if (!data?.url.trim()) return;
    try {
      await schedulesApi.addUrl(schedule.id, configLinkId, {
        url: data.url,
        label: data.label || null,
      });
      setNewUrls((prev) => ({ ...prev, [configLinkId]: { url: '', label: '' } }));
      loadSchedule(schedule.id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed');
    }
  }

  async function handleRemoveUrl(urlId: string) {
    if (!schedule) return;
    try {
      await schedulesApi.removeUrl(schedule.id, urlId);
      loadSchedule(schedule.id);
    } catch (err) {
      console.error(err);
    }
  }

  function getNewUrl(linkId: string) {
    return newUrls[linkId] || { url: '', label: '' };
  }

  function setNewUrlField(linkId: string, field: 'url' | 'label', value: string) {
    setNewUrls((prev) => ({
      ...prev,
      [linkId]: { ...getNewUrl(linkId), [field]: value },
    }));
  }

  if (loading) {
    return <div className="loading-overlay"><div className="spinner" /></div>;
  }

  if (error || !schedule) {
    return (
      <div className="animate-in">
        <div className="card" style={{ padding: 40, textAlign: 'center' }}>
          <div className="empty-state-icon"><IconCalendar size={48} /></div>
          <div className="empty-state-text">{error || 'Schedule not found'}</div>
          <Link to="/schedules" className="btn btn-secondary" style={{ marginTop: 16 }}>← Back</Link>
        </div>
      </div>
    );
  }

  const totalUrls = schedule.config_links.reduce((sum, cl) => sum + cl.url_targets.length, 0);

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title">{schedule.name}</h1>
          <p className="page-subtitle">{schedule.description || 'No description'}</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <Link to={`/schedules/${schedule.id}/edit`} className="btn btn-primary">
            <IconEdit size={16} /> Edit
          </Link>
          <button className="btn btn-secondary" onClick={handleTrigger}>
            <IconPlay size={16} /> Trigger Now
          </button>
          <button className="btn btn-secondary" onClick={handleToggle}>
            <IconPause size={16} /> {schedule.is_active ? 'Pause' : 'Activate'}
          </button>
          <button className="btn btn-secondary" onClick={handleDelete}
            style={{ borderColor: 'var(--status-failed)', color: 'var(--status-failed)' }}>
            <IconTrash size={16} /> Delete
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 24 }}>

        {/* ── Schedule Info ── */}
        <div className="card" style={{ padding: 28 }}>
          <h3 className="card-title" style={{ marginBottom: 20 }}>Schedule Info</h3>
          <div className="detail-grid">
            <Row label="Status" value={
              <span className={`badge badge--${schedule.is_active ? 'success' : 'cancelled'}`}>
                {schedule.is_active ? 'Active' : 'Paused'}
              </span>
            } />
            <Row label="Type" value={
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                {schedule.cron_expression ? <><IconCalendar size={14} /> {schedule.cron_expression}</> :
                  <><IconClock size={14} /> Every {schedule.interval_seconds! >= 3600
                    ? `${Math.round(schedule.interval_seconds! / 3600)}h`
                    : `${Math.round(schedule.interval_seconds! / 60)}m`}</>}
              </span>
            } />
            <Row label="Timezone" value={schedule.timezone} />
            <Row label="Queue" value={schedule.default_queue} />
            <Row label="Next Run" value={schedule.next_run_at ? new Date(schedule.next_run_at).toLocaleString() : '—'} />
            <Row label="Last Run" value={schedule.last_run_at ? new Date(schedule.last_run_at).toLocaleString() : '—'} />
            <Row label="Total Runs" value={schedule.run_count.toString()} />
            <Row label="Configs" value={`${schedule.config_links.length} configs, ${totalUrls} URLs`} />
            <Row label="ID" value={schedule.id} mono />
          </div>
        </div>

        {/* ── Callback ── */}
        <div className="card" style={{ padding: 28 }}>
          <h3 className="card-title" style={{ marginBottom: 20 }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <IconWebhook size={18} /> Callback
            </span>
          </h3>
          {schedule.callback ? (
            <div className="detail-grid">
              <Row label="URL" value={schedule.callback.url} mono />
              <Row label="Method" value={
                <span className="badge badge--queued">{schedule.callback.method}</span>
              } />
              <Row label="Active" value={
                <span className={`badge badge--${schedule.callback.is_active ? 'success' : 'cancelled'}`}>
                  {schedule.callback.is_active ? 'Yes' : 'No'}
                </span>
              } />
              <Row label="Batch" value={schedule.callback.batch_results ? 'Yes' : 'No'} />
              <Row label="Retries" value={`${schedule.callback.retry_count}x / ${schedule.callback.retry_delay_seconds}s delay`} />
            </div>
          ) : (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No callback configured</p>
          )}
        </div>

        {/* ── Email Notification ── */}
        <div className="card" style={{ padding: 28 }}>
          <h3 className="card-title" style={{ marginBottom: 20 }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <IconMail size={18} /> Email Notification
            </span>
          </h3>
          {schedule.email_notification ? (
            <div className="detail-grid">
              <Row label="Recipients" value={
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {schedule.email_notification.recipient_emails.map((email, i) => (
                    <span key={i} className="badge badge--queued" style={{ fontSize: '0.75rem' }}>{email}</span>
                  ))}
                </div>
              } />
              <Row label="Subject" value={schedule.email_notification.subject_template} />
              <Row label="Active" value={
                <span className={`badge badge--${schedule.email_notification.is_active ? 'success' : 'cancelled'}`}>
                  {schedule.email_notification.is_active ? 'Yes' : 'No'}
                </span>
              } />
              <Row label="On Success" value={
                <span className={`badge badge--${schedule.email_notification.on_success ? 'success' : 'cancelled'}`}>
                  {schedule.email_notification.on_success ? 'Yes' : 'No'}
                </span>
              } />
              <Row label="On Failure" value={
                <span className={`badge badge--${schedule.email_notification.on_failure ? 'success' : 'cancelled'}`}>
                  {schedule.email_notification.on_failure ? 'Yes' : 'No'}
                </span>
              } />
              <Row label="Batch" value={schedule.email_notification.batch_results ? 'Yes' : 'No'} />
            </div>
          ) : (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No email notification configured</p>
          )}
        </div>
      </div>

      {/* ── Config Links with URLs / Proxy Source Links ── */}
      <div style={{ marginTop: 24, display: 'flex', flexDirection: 'column', gap: 20 }}>
        {schedule.schedule_type === 'proxy_source' && schedule.proxy_source_links.map((link) => (
          <div key={link.id} className="card" style={{
            padding: 28,
            border: '1px solid var(--accent-cyan)',
            boxShadow: '0 0 12px rgba(0,240,255,0.04)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <h3 className="card-title" style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
                <IconGlobe size={16} />
                <Link to={`/proxy-sources/${link.proxy_source_id}`}
                  style={{ color: 'var(--accent-cyan)', textDecoration: 'none' }}>
                  {link.proxy_source_name || link.proxy_source_id.slice(0, 8)}
                </Link>
              </h3>
            </div>
          </div>
        ))}

        {schedule.schedule_type === 'crawl' && schedule.config_links.map((link) => (
          <div key={link.id} className="card" style={{
            padding: 28,
            border: '1px solid var(--accent-cyan)',
            boxShadow: '0 0 12px rgba(0,240,255,0.04)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h3 className="card-title" style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
                <IconLink size={16} />
                <Link to={`/configurations/${link.config_id}`}
                  style={{ color: 'var(--accent-cyan)', textDecoration: 'none' }}>
                  {link.config_name || link.config_id.slice(0, 8)}
                </Link>
                <span className="badge badge--queued" style={{ marginLeft: 8 }}>
                  {link.url_targets.length} URL{link.url_targets.length !== 1 ? 's' : ''}
                </span>
              </h3>
            </div>

            {/* URL list */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
              {link.url_targets.map((t) => (
                <div key={t.id} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '8px 12px',
                  background: 'var(--bg-tertiary)',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-subtle)',
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize: '0.82rem', color: 'var(--text-primary)',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {t.url}
                    </div>
                    {t.label && <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{t.label}</div>}
                  </div>
                  <button className="action-btn" onClick={() => handleRemoveUrl(t.id)}>
                    <IconTrash size={14} />
                  </button>
                </div>
              ))}
            </div>

            {/* Add URL form */}
            <div style={{ display: 'flex', gap: 8 }}>
              <input type="url" className="form-input" placeholder="https://example.com"
                value={getNewUrl(link.id).url}
                onChange={(e) => setNewUrlField(link.id, 'url', e.target.value)}
                style={{ flex: 2 }} />
              <input type="text" className="form-input" placeholder="Label"
                value={getNewUrl(link.id).label}
                onChange={(e) => setNewUrlField(link.id, 'label', e.target.value)}
                style={{ flex: 1 }} />
              <button type="button" className="btn btn-secondary"
                onClick={() => handleAddUrl(link.id)}
                disabled={!getNewUrl(link.id).url.trim()}>
                <IconPlus size={14} />
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* ── Callback Logs ── */}
      {schedule.callback && logs.length > 0 && (
        <div className="card table-card" style={{ marginTop: 24 }}>
          <div style={{ padding: '18px 24px 0' }}>
            <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              Callback Logs
              <button className="action-btn" onClick={() => loadSchedule(schedule.id)}>
                <IconRefresh size={14} />
              </button>
            </h3>
          </div>
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Status</th>
                <th>HTTP</th>
                <th>Duration</th>
                <th>Attempt</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id}>
                  <td style={{ fontSize: '0.8rem' }}>{new Date(log.created_at).toLocaleString()}</td>
                  <td>
                    <span className={`badge badge--${log.success ? 'success' : 'failed'}`}>
                      {log.success ? 'OK' : 'Failed'}
                    </span>
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
                    {log.response_status || '—'}
                  </td>
                  <td style={{ fontSize: '0.8rem' }}>{log.duration_ms}ms</td>
                  <td style={{ fontSize: '0.8rem' }}>#{log.attempt_number}</td>
                  <td style={{ fontSize: '0.78rem', color: 'var(--status-failed)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {log.error_message || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Email Notification Logs ── */}
      {schedule.email_notification && emailLogs.length > 0 && (
        <div className="card table-card" style={{ marginTop: 24 }}>
          <div style={{ padding: '18px 24px 0' }}>
            <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <IconMail size={16} /> Email Notification Logs
              <button className="action-btn" onClick={() => loadSchedule(schedule!.id)}>
                <IconRefresh size={14} />
              </button>
            </h3>
          </div>
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Trigger</th>
                <th>Status</th>
                <th>Duration</th>
                <th>Attempt</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {emailLogs.map((log) => (
                <tr key={log.id}>
                  <td style={{ fontSize: '0.8rem' }}>{new Date(log.created_at).toLocaleString()}</td>
                  <td>
                    <span className={`badge badge--${log.trigger_reason === 'success' ? 'success' : 'failed'}`}>
                      {log.trigger_reason}
                    </span>
                  </td>
                  <td>
                    <span className={`badge badge--${log.success ? 'success' : 'failed'}`}>
                      {log.success ? 'Sent' : 'Failed'}
                    </span>
                  </td>
                  <td style={{ fontSize: '0.8rem' }}>{log.duration_ms}ms</td>
                  <td style={{ fontSize: '0.8rem' }}>#{log.attempt_number}</td>
                  <td style={{ fontSize: '0.78rem', color: 'var(--status-failed)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {log.error_message || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
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
