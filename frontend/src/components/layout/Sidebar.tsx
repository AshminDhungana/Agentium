import { forwardRef } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import type { NavGroup, NavItem } from './navConfig';
import { useWebSocketStore } from '@/store/websocketStore';
import { useAuthStore } from '@/store/authStore';
import { VoiceIndicator } from '@/components/VoiceIndicator';
import { Shield, LogOut } from 'lucide-react';

interface SidebarProps {
  groups: NavGroup[];
  sovereignItem?: NavItem;
  collapsed: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

const prefetch = (path: string) => {
  switch (path) {
    case '/chat':         import('@/pages/ChatPage');           break;
    case '/agents':       import('@/pages/AgentsPage');         break;
    case '/tasks':        import('@/pages/TasksPage');          break;
    case '/monitoring':   import('@/pages/MonitoringPage');     break;
    case '/voting':       import('@/pages/VotingPage');         break;
    case '/constitution': import('@/pages/ConstitutionPage');   break;
    case '/models':       import('@/pages/ModelsPage');         break;
    case '/channels':     import('@/pages/ChannelsPage');       break;
    case '/message-log':  import('@/pages/MessageLogPage');     break;
    case '/ab-testing':   import('@/pages/ABTestingPage');      break;
    case '/settings':     import('@/pages/SettingsPage');       break;
    case '/sovereign':    import('@/pages/SovereignDashboard'); break;
    default:              import('@/pages/Dashboard');          break;
  }
};

export const Sidebar = forwardRef<HTMLElement, SidebarProps>(function Sidebar(
  { groups, sovereignItem, collapsed, mobileOpen, onCloseMobile },
  ref
) {
  const unreadCount = useWebSocketStore((s) => s.unreadCount);
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = () => {
    window.dispatchEvent(new Event('logout'));
    logout();
    navigate('/login');
  };

  const isActive = (path: string) =>
    path === '/' ? location.pathname === '/' : location.pathname.startsWith(path);

  const renderItem = (item: NavItem) => {
    const active = isActive(item.path);
    const danger = item.variant === 'danger';
    const badge = item.path === '/chat' && unreadCount > 0 ? unreadCount : item.badge;
    return (
      <NavLink
        key={item.path}
        to={item.path}
        end={item.path === '/'}
        aria-current={active ? 'page' : undefined}
        title={collapsed ? item.label : undefined}
        onMouseEnter={() => prefetch(item.path)}
        onClick={mobileOpen ? onCloseMobile : undefined}
        className={({ isActive: a }) =>
          `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200 ${
            danger
              ? a
                ? 'border border-red-200 bg-red-50 text-red-700 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-300'
                : 'bg-red-50/50 text-red-600 hover:bg-red-50 dark:bg-red-500/5 dark:text-red-400 dark:hover:bg-red-500/10'
              : a
                ? 'bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300'
                : 'text-gray-700 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-white/5'
          } ${collapsed ? 'justify-center' : ''}`
        }
      >
        <item.icon className={`h-[18px] w-[18px] flex-shrink-0 ${danger ? 'text-red-600' : ''}`} aria-hidden="true" />
        {!collapsed && <span className="flex-1 truncate">{item.label}</span>}
        {!collapsed && badge !== undefined && (
          <span aria-live="polite" className="min-w-[18px] rounded-full bg-red-500 px-1.5 py-0.5 text-center text-xs font-bold text-white">
            {badge > 9 ? '9+' : badge}
          </span>
        )}
      </NavLink>
    );
  };

  return (
    <aside
      ref={ref}
      tabIndex={-1}
      aria-label="Primary"
      className={[
        'flex flex-col border-r border-gray-200 bg-white dark:border-[#1e2535] dark:bg-[#161b27]',
        'fixed inset-y-0 left-0 z-40 w-64 transform transition-transform duration-300 ease-out motion-reduce:transition-none',
        'lg:static lg:z-auto lg:translate-x-0',
        collapsed ? 'lg:w-[72px]' : 'lg:w-64',
        mobileOpen ? 'translate-x-0' : '-translate-x-full',
      ].join(' ')}
    >
      <div className="flex h-14 flex-shrink-0 items-center gap-2 border-b border-gray-200 px-4 dark:border-[#1e2535]">
        <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-blue-600 text-white">
          <Shield className="h-5 w-5" aria-hidden="true" />
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <p className="truncate text-base font-bold text-gray-900 dark:text-white">Agentium</p>
            <p className="truncate text-xs text-gray-600 dark:text-blue-400/70">AI Governance</p>
          </div>
        )}
      </div>

      <nav className="flex-1 space-y-4 overflow-y-auto px-3 py-3" aria-label="Main navigation">
        {groups.map((group) => (
          <div key={group.id} className="space-y-0.5">
            {!collapsed && (
              <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                {group.label}
              </p>
            )}
            {group.items.map(renderItem)}
          </div>
        ))}
        {sovereignItem && (
          <div className="space-y-0.5 border-t border-gray-200 pt-3 dark:border-[#1e2535]">
            {renderItem(sovereignItem)}
          </div>
        )}
      </nav>

      <div className="flex-shrink-0 border-t border-gray-200 px-4 py-3 dark:border-[#1e2535]">
        <div className={collapsed ? 'flex justify-center' : 'flex items-center gap-3'}>
          <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center overflow-hidden rounded-full bg-gradient-to-br from-purple-500 to-pink-500 text-sm font-bold text-white">
            {user?.avatar_url ? (
              <img src={user.avatar_url} alt={user?.username || 'User'} className="h-full w-full object-cover" />
            ) : (
              user?.username?.charAt(0).toUpperCase() || 'U'
            )}
          </div>
          {!collapsed && (
            <>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-gray-900 dark:text-white">{user?.username || 'User'}</p>
                <p className="truncate text-xs capitalize text-gray-600 dark:text-gray-400">{user?.role || 'Member'}</p>
              </div>
              <VoiceIndicator iconOnly />
            </>
          )}
        </div>
        {!collapsed && (
          <button
            onClick={handleLogout}
            className="mt-2 flex w-full items-center gap-2 rounded-lg px-3 py-1.5 text-sm text-red-600 transition-colors hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-500/10"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
            Logout
          </button>
        )}
      </div>
    </aside>
  );
});
