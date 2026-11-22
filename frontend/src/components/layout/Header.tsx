import { IconSearch, IconBell, IconLogout } from '../icons/Icons';
import { useNavigate } from 'react-router-dom';
import { logout } from '../../api/auth';

export default function Header() {
  const navigate = useNavigate();

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
        <button
          className="btn-ghost"
          title="Sign out"
          onClick={() => {
            logout();
            navigate('/login', { replace: true });
          }}
        >
          <IconLogout size={18} />
        </button>
      </div>
    </header>
  );
}
