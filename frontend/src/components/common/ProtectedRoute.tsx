import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';

interface ProtectedRouteProps {
    children: React.ReactNode;
    requireSovereign?: boolean;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
    children,
    requireSovereign = false
}) => {
    const { user } = useAuthStore();

    if (!user?.isAuthenticated) {
        return <Navigate to="/login" replace />;
    }

    // Check if user is sovereign (admin)
    if (requireSovereign && user.role !== 'admin' && user.username !== 'sovereign') {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="text-center p-8 bg-red-500/10 rounded-lg border border-red-500/20">
                    <h2 className="text-2xl font-bold text-red-400 mb-2">Access Denied</h2>
                    <p className="text-gray-400">Only the Sovereign can access this area.</p>
                </div>
            </div>
        );
    }

    return <>{children}</>;
};