import { IconSearch, IconBell } from '../icons/Icons';

export default function Header() {
  return (
    <header className="header">
      <div className="header-search">
        <IconSearch size={16} />
        <input type="text" placeholder="Search crawls, configs..." />
      </div>

      <div className="header-actions">
        <button className="btn-ghost" title="Notifications">
          <IconBell size={18} />
        </button>
        <div className="header-profile">
          <span className="header-profile-name">Admin Profile</span>
          <div className="header-profile-avatar">AP</div>
        </div>
      </div>
    </header>
  );
}
