import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';

interface Props {
    children: ReactNode;
    variant?: 'page' | 'widget';
    fallbackHeading?: string;
}

interface State {
    hasError: boolean;
    error: Error | null;
    isRetrying: boolean;
    lastErrorKey: number;
}

export class ErrorBoundary extends Component<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = {
            hasError: false,
            error: null,
            isRetrying: false,
            lastErrorKey: Date.now()
        };
    }

    static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error, isRetrying: false, lastErrorKey: Date.now() };
    }

    componentDidCatch(error: Error, errorInfo: ErrorInfo) {
        console.error('ErrorBoundary caught an error:', error, errorInfo);
        this.reportError(error, errorInfo);
    }

    reportError = async (error: Error, errorInfo: ErrorInfo) => {
        try {
            const payload = {
                message: error.message || 'Unknown frontend error',
                name: error.name || 'Error',
                stack: error.stack || '',
                component_stack: errorInfo.componentStack || '',
                url: window.location.href
            };

            // Get base URL gracefully if running via Vite 
            const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
            
            // Try to pull auth token if logged in
            let token = '';
            try {
                const authStorage = localStorage.getItem('auth-storage');
                if (authStorage) {
                    const parsed = JSON.parse(authStorage);
                    token = parsed?.state?.token || '';
                }
            } catch (e) {
                // Ignore parse errors
            }

            const headers: Record<string, string> = {
                'Content-Type': 'application/json'
            };
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }

            await fetch(`${baseUrl}/api/v1/monitoring/frontend/errors`, {
                method: 'POST',
                headers,
                body: JSON.stringify(payload)
            });
        } catch (e) {
            // Silently fail if telemetry posting fails (avoids endless error loops)
        }
    }

    handleRetry = () => {
        this.setState({ isRetrying: true });
        
        // Small delay for UI feedback
        setTimeout(() => {
            this.setState({
                hasError: false,
                error: null,
                isRetrying: false,
                lastErrorKey: Date.now()
            });
        }, 400);
    }

    render() {
        if (this.state.hasError) {
            const { variant = 'widget', fallbackHeading = 'Something went wrong' } = this.props;

            if (variant === 'widget') {
                return (
                    <div className="w-full h-full min-h-[150px] flex flex-col items-center justify-center p-4 bg-red-50/50 dark:bg-red-950/20 border border-red-100 dark:border-red-900/50 rounded-xl text-center">
                        <AlertTriangle className="w-8 h-8 text-red-500 mb-2 opacity-80" />
                        <h3 className="text-sm font-bold text-red-900 dark:text-red-300 mb-1">{fallbackHeading}</h3>
                        <p className="text-xs text-red-700 dark:text-red-400 mb-3 max-w-[200px] truncate opacity-80">
                            {this.state.error?.message}
                        </p>
                        <button 
                            onClick={this.handleRetry}
                            disabled={this.state.isRetrying}
                            className="flex items-center justify-center gap-1.5 px-3 py-1.5 w-full bg-red-100 hover:bg-red-200 dark:bg-red-900/50 dark:hover:bg-red-900/70 text-red-800 dark:text-red-200 text-xs font-semibold rounded-lg transition-colors disabled:opacity-50"
                        >
                            <RotateCcw className={`w-3 h-3 ${this.state.isRetrying ? 'animate-spin' : ''}`} />
                            {this.state.isRetrying ? 'Retrying...' : 'Retry'}
                        </button>
                    </div>
                );
            }

            return (
                <div className="flex-1 w-full h-full min-h-[400px] flex flex-col items-center justify-center p-6 animate-in fade-in duration-300">
                    <div className="max-w-md w-full bg-white dark:bg-[#0f1117] border border-red-200 dark:border-red-900/50 rounded-2xl shadow-lg p-8 text-center">
                        <div className="w-16 h-16 bg-red-100 dark:bg-red-900/30 rounded-full flex items-center justify-center mx-auto mb-4 border border-red-200 dark:border-red-800/50">
                            <AlertTriangle className="w-8 h-8 text-red-600 dark:text-red-400" />
                        </div>
                        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-2">{fallbackHeading}</h2>
                        <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
                            A critical rendering error occurred in this view. We've automatically logged this issue.
                        </p>
                        
                        <div className="bg-gray-50 dark:bg-gray-950 rounded-lg p-3 text-left overflow-hidden mb-6 border border-gray-200 dark:border-[#1e2535]">
                            <p className="text-xs font-mono text-red-600 dark:text-red-400 truncate w-full">
                                {this.state.error?.toString()}
                            </p>
                        </div>

                        <div className="flex flex-wrap gap-3 justify-center">
                            <button 
                                onClick={() => window.location.reload()}
                                className="px-4 py-2 bg-gray-100 hover:bg-gray-200 dark:bg-[#161b27] dark:hover:bg-gray-700 text-gray-900 dark:text-white text-sm font-semibold rounded-lg transition-colors"
                            >
                                Reload Page
                            </button>
                            <button 
                                onClick={this.handleRetry}
                                disabled={this.state.isRetrying}
                                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg transition-colors flex items-center gap-2 disabled:opacity-50"
                            >
                                {this.state.isRetrying ? (
                                    <><RotateCcw className="w-4 h-4 animate-spin" /> Retrying...</>
                                ) : (
                                    <><RotateCcw className="w-4 h-4" /> Try Again</>
                                )}
                            </button>
                        </div>
                    </div>
                </div>
            );
        }

        return <React.Fragment key={this.state.lastErrorKey}>{this.props.children}</React.Fragment>;
    }
}
