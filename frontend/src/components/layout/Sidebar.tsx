import { NavLink } from 'react-router-dom';
import { IconDashboard, IconConfig, IconCalendar, IconFlask, IconClipboard, IconSettings } from '../icons/Icons';

const navItems = [
  { to: '/', label: 'Dashboard', icon: <IconDashboard size={18} /> },
  { to: '/configurations', label: 'Configurations', icon: <IconConfig size={18} /> },
  { to: '/schedules', label: 'Schedules', icon: <IconCalendar size={18} /> },
  { to: '/scrape', label: 'Scrape Playground', icon: <IconFlask size={18} /> },
  { to: '/jobs', label: 'Jobs', icon: <IconClipboard size={18} /> },
  { to: '/settings', label: 'Settings', icon: <IconSettings size={18} /> },
];

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <img src="/logo.png" alt="Pilgrim" className="sidebar-brand-logo" />
      </div>

      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `sidebar-link${isActive ? ' active' : ''}`
            }
          >
            <span className="sidebar-link-icon">{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-version">Pilgrim v0.1.0</div>
    </aside>
  );
}
