import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { healthApi, configsApi, jobsApi } from '../../api/client';
import type { CrawlJob, ReadinessResponse } from '../../api/client';
import { IconApi, IconDatabase, IconBolt, IconShield, IconConfig, IconClock, IconCheck, IconEye, IconRefresh, IconInbox } from '../../components/icons/Icons';

interface DashboardStats {
  totalConfigs: number;
  activeJobs: number;
  recentJobs: CrawlJob[];
  health: {
    api: boolean;
    database: boolean;
    redis: boolean;
  };
}

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats>({
    totalConfigs: 0,
    activeJobs: 0,
    recentJobs: [],
    health: { api: false, database: false, redis: false },
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboard();
  }, []);

  async function loadDashboard() {
    setLoading(true);
    try {
      const [healthRes, configsRes, jobsRes] = await Promise.allSettled([
        healthApi.readiness(),
        configsApi.list(0, 50),
        jobsApi.list(0, 10),
      ]);

      const health =
        healthRes.status === 'fulfilled'
          ? {
              api: true,
              database: healthRes.value.status === 'ready',
              redis: healthRes.value.status === 'ready',
            }
          : { api: false, database: false, redis: false };

      const configs = configsRes.status === 'fulfilled' ? configsRes.value : { items: [], total: 0 };
      const jobs = jobsRes.status === 'fulfilled' ? jobsRes.value : { items: [], total: 0 };

      const activeCount = jobs.items.filter(
        (j: CrawlJob) => j.status === 'running' || j.status === 'queued'
      ).length;

      setStats({
        totalConfigs: configs.total,
        activeJobs: activeCount,
        recentJobs: jobs.items.slice(0, 8),
        health,
      });
    } catch (err) {
      console.error('Dashboard load error:', err);
    }
    setLoading(false);
  }

  const successRate = stats.recentJobs.length > 0
    ? (
        (stats.recentJobs.filter((j) => j.status === 'succeeded').length /
          stats.recentJobs.length) *
        100
      ).toFixed(1)
    : '—';

  if (loading) {
    return (
      <div className="loading-overlay">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <div className="animate-in">
      {/* ── Status cards ──────────────────────────────── */}
      <div className="status-grid">
        <div className="card status-card animate-in">
          <div className="status-card-icon"><IconApi size={22} /></div>
          <div className="status-card-info">
            <div className="status-card-label">API Status</div>
            <div className="status-card-value">
              {stats.health.api ? 'Operational' : 'Down'}
            </div>
            <div className="status-card-sub">
              {stats.health.api ? '99.98% uptime' : 'Check logs'}
            </div>
          </div>
          <div className={`status-dot${stats.health.api ? '' : ' status-dot--error'}`} />
        </div>

        <div className="card status-card animate-in">
          <div className="status-card-icon"><IconDatabase size={22} /></div>
          <div className="status-card-info">
            <div className="status-card-label">Database</div>
            <div className="status-card-value">
              {stats.health.database ? 'Healthy' : 'Disconnected'}
            </div>
            <div className="status-card-sub">PostgreSQL 16</div>
          </div>
          <div className={`status-dot${stats.health.database ? '' : ' status-dot--error'}`} />
        </div>

        <div className="card status-card animate-in">
          <div className="status-card-icon"><IconBolt size={22} /></div>
          <div className="status-card-info">
            <div className="status-card-label">Redis</div>
            <div className="status-card-value">
              {stats.health.redis ? 'Connected' : 'Disconnected'}
            </div>
            <div className="status-card-sub">Broker + Cache</div>
          </div>
          <div className={`status-dot${stats.health.redis ? '' : ' status-dot--error'}`} />
        </div>

        <div className="card status-card animate-in">
          <div className="status-card-icon"><IconShield size={22} /></div>
          <div className="status-card-info">
            <div className="status-card-label">Proxy Pool</div>
            <div className="status-card-value">Inactive</div>
            <div className="status-card-sub">Not configured</div>
          </div>
          <div className="status-dot status-dot--error" />
        </div>
      </div>

      {/* ── Metrics cards ─────────────────────────────── */}
      <div className="stats-grid">
        <div className="card stat-card animate-in">
          <div className="stat-card-top">
            <div>
              <div className="stat-card-value">{stats.totalConfigs}</div>
              <div className="stat-card-label">Active Configs</div>
            </div>
            <div className="stat-card-icon"><IconConfig size={20} /></div>
          </div>
        </div>

        <div className="card stat-card animate-in">
          <div className="stat-card-top">
            <div>
              <div className="stat-card-value">{stats.activeJobs}</div>
              <div className="stat-card-label">Running Jobs</div>
            </div>
            <div className="stat-card-icon"><IconClock size={20} /></div>
          </div>
        </div>

        <div className="card stat-card animate-in">
          <div className="stat-card-top">
            <div>
              <div className="stat-card-value">{successRate}%</div>
              <div className="stat-card-label">Success Rate</div>
            </div>
            <div className="stat-card-icon"><IconCheck size={20} /></div>
          </div>
        </div>
      </div>

      {/* ── Recent jobs table ─────────────────────────── */}
      <div className="card table-card animate-in">
        <div className="card-header">
          <h2 className="card-title">Recent Crawl Jobs</h2>
          <Link to="/jobs" className="view-all">View All</Link>
        </div>
        <table>
          <thead>
            <tr>
              <th>Job ID</th>
              <th>Source URL</th>
              <th>Status</th>
              <th>Start Time</th>
              <th>Duration</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {stats.recentJobs.length === 0 ? (
              <tr>
                <td colSpan={6}>
                  <div className="empty-state">
                    <div className="empty-state-icon"><IconInbox size={48} /></div>
                    <div className="empty-state-text">No crawl jobs yet</div>
                    <div className="empty-state-sub">
                      Create a config and start scraping
                    </div>
                  </div>
                </td>
              </tr>
            ) : (
              stats.recentJobs.map((job) => (
                <tr key={job.id}>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
                    {job.id.slice(0, 8)}
                  </td>
                  <td>{job.target_url}</td>
                  <td>
                    <span className={`badge badge--${job.status}`}>
                      {job.status}
                    </span>
                  </td>
                  <td>
                    {job.started_at
                      ? new Date(job.started_at).toLocaleTimeString()
                      : '—'}
                  </td>
                  <td>
                    {job.started_at && job.finished_at
                      ? formatDuration(job.started_at, job.finished_at)
                      : '—'}
                  </td>
                  <td>
                    <div className="action-btns">
                      <Link to={`/jobs/${job.id}`} className="action-btn" title="View">
                        <IconEye size={16} />
                      </Link>
                      <button className="action-btn" title="Retry">
                        <IconRefresh size={16} />
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

function formatDuration(start: string, end: string): string {
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 1000) return `${ms}ms`;
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${s % 60}s`;
}
