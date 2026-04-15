import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { schedulesApi } from '../../api/client';
import type { Schedule } from '../../api/client';
import { IconPlus, IconEye, IconPlay, IconTrash, IconCalendar, IconClock, IconPause } from '../../components/icons/Icons';

export default function Schedules() {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSchedules();
  }, []);

  async function loadSchedules() {
    setLoading(true);
    try {
      const res = await schedulesApi.list(0, 100);
      setSchedules(res.items);
      setTotal(res.total);
    } catch (err) {
      console.error('Failed to load schedules:', err);
    }
    setLoading(false);
  }

  async function handleTrigger(id: string, name: string) {
    if (!confirm(`Trigger schedule "${name}" now?`)) return;
    try {
      const res = await schedulesApi.trigger(id);
      alert(`Triggered: ${res.jobs_created} jobs created`);
      loadSchedules();
    } catch (err) {
      console.error('Trigger failed:', err);
    }
  }

  async function handleDelete(id: string, name: string) {
    if (!confirm(`Delete schedule "${name}"?`)) return;
    try {
      await schedulesApi.delete(id);
      setSchedules((prev) => prev.filter((s) => s.id !== id));
      setTotal((prev) => prev - 1);
    } catch (err) {
      console.error('Delete failed:', err);
    }
  }

  async function handleToggle(schedule: Schedule) {
    try {
      await schedulesApi.update(schedule.id, { is_active: !schedule.is_active } as Partial<Schedule>);
      loadSchedules();
    } catch (err) {
      console.error('Toggle failed:', err);
    }
  }

  function formatScheduleType(s: Schedule): string {
    if (s.cron_expression) return s.cron_expression;
    if (s.interval_seconds) {
      if (s.interval_seconds >= 3600) return `Every ${Math.round(s.interval_seconds / 3600)}h`;
      if (s.interval_seconds >= 60) return `Every ${Math.round(s.interval_seconds / 60)}m`;
      return `Every ${s.interval_seconds}s`;
    }
    return '—';
  }

  function formatRelativeTime(dt: string | null): string {
    if (!dt) return '—';
    const diff = new Date(dt).getTime() - Date.now();
    if (diff < 0) return 'Overdue';
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `in ${mins}m`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `in ${hours}h`;
    return `in ${Math.floor(hours / 24)}d`;
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
          <h1 className="page-title">Schedules</h1>
          <p className="page-subtitle">{total} schedule{total !== 1 ? 's' : ''} registered</p>
        </div>
        <Link to="/schedules/new" className="btn btn-primary">
          <IconPlus size={16} /> New Schedule
        </Link>
      </div>

      <div className="card table-card">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Schedule</th>
              <th>Configs</th>
              <th>URLs</th>
              <th>Status</th>
              <th>Next Run</th>
              <th>Runs</th>
              <th>Callback</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {schedules.length === 0 ? (
              <tr>
                <td colSpan={9}>
                  <div className="empty-state">
                    <div className="empty-state-icon"><IconCalendar size={48} /></div>
                    <div className="empty-state-text">No schedules yet</div>
                    <div className="empty-state-sub">
                      Create a schedule to automate your crawl jobs
                    </div>
                  </div>
                </td>
              </tr>
            ) : (
              schedules.map((schedule) => (
                <tr key={schedule.id}>
                  <td>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                      {schedule.name}
                    </div>
                    {schedule.description && (
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 2 }}>
                        {schedule.description.slice(0, 60)}
                        {schedule.description.length > 60 ? '…' : ''}
                      </div>
                    )}
                  </td>
                  <td>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.8rem' }}>
                      {schedule.cron_expression ? <IconCalendar size={13} /> : <IconClock size={13} />}
                      {formatScheduleType(schedule)}
                    </span>
                  </td>
                  <td>
                    <span className="badge badge--queued">{schedule.config_links.length}</span>
                  </td>
                  <td>
                    <span className="badge badge--queued">
                      {schedule.config_links.reduce((sum, cl) => sum + cl.url_targets.length, 0)}
                    </span>
                  </td>
                  <td>
                    <span className={`badge badge--${schedule.is_active ? 'success' : 'cancelled'}`}>
                      {schedule.is_active ? 'Active' : 'Paused'}
                    </span>
                  </td>
                  <td style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                    {formatRelativeTime(schedule.next_run_at)}
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
                    {schedule.run_count}
                  </td>
                  <td>
                    {schedule.callback ? (
                      <span className={`badge badge--${schedule.callback.is_active ? 'success' : 'cancelled'}`}>
                        {schedule.callback.method}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>—</span>
                    )}
                  </td>
                  <td>
                    <div className="action-btns">
                      <Link to={`/schedules/${schedule.id}`} className="action-btn" title="View">
                        <IconEye size={16} />
                      </Link>
                      <button className="action-btn" title="Trigger Now"
                        onClick={() => handleTrigger(schedule.id, schedule.name)}>
                        <IconPlay size={16} />
                      </button>
                      <button className="action-btn" title={schedule.is_active ? 'Pause' : 'Activate'}
                        onClick={() => handleToggle(schedule)}>
                        <IconPause size={16} />
                      </button>
                      <button className="action-btn" title="Delete"
                        onClick={() => handleDelete(schedule.id, schedule.name)}>
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
