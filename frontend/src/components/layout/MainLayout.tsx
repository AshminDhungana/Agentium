import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';
import { HealthIndicator } from '@/components/HealthIndicator';
import {
    LayoutDashboard,
    Users,
    FileText,
    Settings,
    LogOut,
    Shield,
    Cpu,
    Crown,
    MessageCircle,
    Activity,
    Sun,
    Moon
} from 'lucide-react';
import { useEffect, useState } from 'react';

export function MainLayout() {
    const { user, logout } = useAuthStore();
    const navigate = useNavigate();
    const [isDark, setIsDark] = useState(() => {
        if (typeof window !== 'undefined') {
            return document.documentElement.classList.contains('dark');
        }
        return false;
    });

    useEffect(() => {
        if (!user?.isAuthenticated) {
            navigate('/login');
        }
    }, [user, navigate]);

    const toggleTheme = () => {
        const newDark = !isDark;
        setIsDark(newDark);
        
        if (newDark) {
            document.documentElement.classList.add('dark');
            localStorage.setItem('theme', 'dark');
        } else {
            document.documentElement.classList.remove('dark');
            localStorage.setItem('theme', 'light');
        }
    };

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    const navItems = [
        { path: '/', label: 'Dashboard', icon: LayoutDashboard },
        { path: '/chat', label: 'Command Interface', icon: Crown },
        { path: '/agents', label: 'Agents', icon: Users },
        { path: '/tasks', label: 'Tasks', icon: FileText },
        { path: '/monitoring', label: 'Monitoring', icon: Activity },
        { path: '/channels', label: 'Channels', icon: MessageCircle },
        { path: '/constitution', label: 'Constitution', icon: Shield },
        { path: '/models', label: 'AI Models', icon: Cpu },
        { path: '/settings', label: 'Settings', icon: Settings },
    ];

    return (
        <div className="h-screen bg-gray-50 dark:bg-[#0f1117] flex overflow-hidden">
            {/* Sidebar - Fixed */}
            <aside className="w-64 bg-white dark:bg-[#161b27] border-r border-gray-200 dark:border-[#1e2535] flex flex-col flex-shrink-0 h-full">
                {/* Header */}
                <div className="p-6 border-b border-gray-200 dark:border-[#1e2535] flex-shrink-0">
                    <div className="flex items-center gap-2">
                        {/* Logo as Theme Toggle */}
                        <button
                            onClick={toggleTheme}
                            className="group relative p-2 rounded-xl transition-all duration-300 hover:bg-gray-100 dark:hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                            aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
                            title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
                        >
                            {/* Light Mode Logo - Blue */}
                            <Shield 
                                className="w-8 h-8 text-blue-600 transition-all duration-300 rotate-0 scale-100 dark:rotate-90 dark:scale-0 dark:opacity-0" 
                            />
                            
                            {/* Dark Mode Logo - White/Light with glow */}
                            <Shield 
                                className="w-8 h-8 absolute inset-0 m-auto text-white drop-shadow-[0_0_8px_rgba(255,255,255,0.5)] transition-all duration-300 rotate-90 scale-0 opacity-0 dark:rotate-0 dark:scale-100 dark:opacity-100" 
                            />
                            
                        </button>

                        <div>
                            <h1 className="text-xl font-bold text-gray-900 dark:text-white">Agentium</h1>
                            <p className="text-xs text-gray-500 dark:text-blue-400/70">AI Governance</p>
                        </div>
                    </div>
                </div>

                {/* Navigation - Scrollable if needed */}
                <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
                    {navItems.map((item) => (
                        <NavLink
                            key={item.path}
                            to={item.path}
                            className={({ isActive }) =>
                                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                                    isActive
                                        ? 'bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300'
                                        : 'text-gray-700 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5 dark:hover:text-gray-200'
                                }`
                            }
                        >
                            <item.icon className="w-5 h-5" />
                            {item.label}
                        </NavLink>
                    ))}

                    {/* Sovereign Control – admin only */}
                    {user?.isSovereign && (
                        <NavLink
                            to="/sovereign"
                            className={({ isActive }) =>
                                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                                    isActive
                                        ? 'bg-red-500/20 text-red-600 dark:text-red-400 border-red-500/30'
                                        : 'bg-red-500/10 text-red-600 dark:text-red-400/80 hover:bg-red-500/20 border-red-500/20 dark:border-red-500/15 dark:hover:text-red-400'
                                }`
                            }
                        >
                            <Shield className="w-5 h-5" />
                            Sovereign Control
                        </NavLink>
                    )}
                </nav>

                {/* User Section - Fixed at bottom */}
                <div className="p-4 border-t border-gray-200 dark:border-[#1e2535] flex-shrink-0 bg-white dark:bg-[#161b27]">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="w-8 h-8 rounded-full bg-blue-600 dark:from-blue-500 dark:to-indigo-600 flex items-center justify-center text-white text-sm font-bold">
                            {user?.username?.charAt(0).toUpperCase()}
                        </div>
                        <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                                {user?.username}
                            </p>
                            <p className="text-xs text-gray-500 dark:text-gray-500 capitalize">
                                {user?.role}
                            </p>
                        </div>
                    </div>

                    <button
                        onClick={handleLogout}
                        className="flex w-full items-center gap-2 px-3 py-2 text-sm text-red-600 dark:text-red-400/80 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/10 dark:hover:text-red-400 transition-colors"
                    >
                        <LogOut className="w-4 h-4" />
                        Sign Out
                    </button>
                </div>
            </aside>

            {/* Main Content - Scrollable */}
            <main className="flex-1 relative overflow-hidden">
                {/* Health Indicator - Top Right */}
                <div className="absolute top-3 right-6 z-10">
                    <HealthIndicator />
                </div>

                <div className="h-full overflow-y-auto p-8">
                    <Outlet />
                </div>
            </main>
        </div>
    );
}
