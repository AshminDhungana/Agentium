import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
    children: ReactNode;
}

interface State {
    hasError: boolean;
    error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
    public state: State = {
        hasError: false,
        error: null,
    };

    public static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
        console.error('Uncaught error:', error, errorInfo);
    }

    private handleReload = () => {
        window.location.reload();
    };

    public render() {
        if (this.state.hasError) {
            return (
                <div className="h-screen w-full flex flex-col items-center justify-center bg-gray-50 dark:bg-[#0f1117] p-6 transition-colors duration-200">
                    <div className="bg-white dark:bg-[#161b27] p-8 rounded-2xl border border-gray-200 dark:border-[#1e2535] max-w-md w-full text-center shadow-lg dark:shadow-[0_8px_40px_rgba(0,0,0,0.5)]">

                        {/* Icon */}
                        <div className="inline-flex items-center justify-center w-16 h-16 rounded-xl bg-red-100 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 mb-6">
                            <AlertTriangle className="w-8 h-8 text-red-600 dark:text-red-400" />
                        </div>

                        {/* Title & description */}
                        <h1 className="text-xl font-bold text-gray-900 dark:text-white mb-2">
                            Something went wrong
                        </h1>
                        <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
                            The application encountered an unexpected error.
                        </p>

                        {/* Error detail */}
                        {this.state.error && (
                            <div className="bg-gray-50 dark:bg-[#0f1117] border border-gray-200 dark:border-[#1e2535] p-4 rounded-xl text-left mb-6 overflow-auto max-h-32">
                                <code className="text-xs text-red-600 dark:text-red-400 font-mono break-all">
                                    {this.state.error.message}
                                </code>
                            </div>
                        )}

                        {/* Reload button */}
                        <button
                            onClick={this.handleReload}
                            className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 dark:hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition-colors duration-150 flex items-center justify-center gap-2 shadow-sm"
                        >
                            <RefreshCw className="w-4 h-4" />
                            Reload Application
                        </button>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}
