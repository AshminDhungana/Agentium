import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';
import { Shield } from 'lucide-react';

interface ProtectedRouteProps {
    children: React.ReactNode;
    requireSovereign?: boolean;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
    children,
    requireSovereign = false,
}) => {
    const { user } = useAuthStore();

    if (!user?.isAuthenticated) {
        return <Navigate to="/login" replace />;
    }

    if (requireSovereign && user.role !== 'admin' && user.username !== 'sovereign') {
        return (
            <div className="flex items-center justify-center h-full bg-gray-50 dark:bg-[#0f1117] p-6 transition-colors duration-200">
                <div className="text-center p-8 bg-white dark:bg-[#161b27] rounded-2xl border border-gray-200 dark:border-[#1e2535] shadow-sm dark:shadow-[0_8px_40px_rgba(0,0,0,0.5)] max-w-sm w-full">
                    <div className="inline-flex items-center justify-center w-14 h-14 rounded-xl bg-red-100 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 mb-5">
                        <Shield className="w-7 h-7 text-red-600 dark:text-red-400" />
                    </div>
                    <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
                        Access Denied
                    </h2>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        Only the Sovereign can access this area.
                    </p>
                </div>
            </div>
        );
    }

    return <>{children}</>;
};
