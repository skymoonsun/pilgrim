import { Link } from 'react-router-dom';
import { schedulesApi } from '../../api/client';
import type { Schedule } from '../../api/client';
import { IconPlus, IconEye, IconEdit, IconPlay, IconTrash, IconCalendar, IconClock, IconPause } from '../../components/icons/Icons';
import { useInfiniteScroll } from '../../hooks/useInfiniteScroll';

export default function Schedules() {
  const { items: schedules, total, loading, loadingMore, sentinelRef, reset } = useInfiniteScroll<Schedule>({
    fetchPage: (skip, limit) => schedulesApi.list(skip, limit),
    pageSize: 50,
  });

  async function handleTrigger(id: string, name: string) {
    if (!confirm(`Trigger schedule "${name}" now?`)) return;
    try {
      const res = await schedulesApi.trigger(id);
      alert(`Triggered: ${res.jobs_created} jobs created`);
      reset();
    } catch (err) {
      console.error('Trigger failed:', err);
    }
  }

  async function handleDelete(id: string, name: string) {
    if (!confirm(`Delete schedule "${name}"?`)) return;
    try {
      await schedulesApi.delete(id);
      // Reload to keep totals consistent
      reset();
    } catch (err) {
      console.error('Delete failed:', err);
    }
  }

  async function handleToggle(schedule: Schedule) {
    try {
      await schedulesApi.update(schedule.id, { is_active: !schedule.is_active } as Partial<Schedule>);
      reset();
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

  if (loading && schedules.length === 0) {
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
              <>
                {schedules.map((schedule) => (
                  <tr key={schedule.id}>
                    <td>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                        {schedule.name}
                      </div>
                      <div style={{ display: 'flex', gap: 4, marginTop: 2 }}>
                        <span className={`badge ${schedule.schedule_type === 'proxy_source' ? 'badge--running' : 'badge--queued'}`}>
                          {schedule.schedule_type === 'proxy_source' ? 'Proxy Source' : 'Crawl'}
                        </span>
                        {schedule.description && (
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', lineHeight: '1.5' }}>
                            {schedule.description.slice(0, 40)}{schedule.description.length > 40 ? '…' : ''}
                          </span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: '0.8rem' }}>
                        {schedule.cron_expression ? <IconCalendar size={13} /> : <IconClock size={13} />}
                        {formatScheduleType(schedule)}
                      </span>
                    </td>
                    <td>
                      <span className="badge badge--queued">
                        {schedule.schedule_type === 'proxy_source'
                          ? schedule.proxy_source_links?.length ?? 0
                          : schedule.config_links.length}
                      </span>
                    </td>
                    <td>
                      <span className="badge badge--queued">
                        {schedule.schedule_type === 'proxy_source'
                          ? '—'
                          : schedule.config_links.reduce((sum, cl) => sum + cl.url_targets.length, 0)}
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
                        <Link to={`/schedules/${schedule.id}/edit`} className="action-btn" title="Edit">
                          <IconEdit size={16} />
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
                ))}
                <tr ref={sentinelRef as any}>
                  <td colSpan={9} style={{ textAlign: 'center', padding: '16px 0', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                    {loadingMore && <div className="spinner" style={{ margin: '0 auto' }} />}
                    {!loadingMore && schedules.length < total && <span>Scroll to load more...</span>}
                    {!loadingMore && schedules.length >= total && total > 0 && <span>All schedules loaded</span>}
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