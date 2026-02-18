import React, { useState } from 'react';
import { X, FileText, AlertCircle, Loader2, Sparkles } from 'lucide-react';

interface CreateTaskModalProps {
    onConfirm: (data: { title: string; description: string; priority: string; task_type: string }) => Promise<void>;
    onClose: () => void;
}

const PRIORITY_OPTIONS = [
    { value: 'low', label: 'Low', color: 'blue', description: 'No rush, backlog item' },
    { value: 'normal', label: 'Normal', color: 'emerald', description: 'Standard priority' },
    { value: 'urgent', label: 'Urgent', color: 'orange', description: 'Needs attention soon' },
    { value: 'critical', label: 'Critical', color: 'rose', description: 'Immediate action required' },
] as const;

const TYPE_OPTIONS = [
    { value: 'execution', label: 'Execution', icon: '⚡', description: 'Direct task completion' },
    { value: 'research', label: 'Research', icon: '🔍', description: 'Investigation and analysis' },
    { value: 'creative', label: 'Creative', icon: '✨', description: 'Content and design work' },
] as const;

export const CreateTaskModal: React.FC<CreateTaskModalProps> = ({ onConfirm, onClose }) => {
    const [title, setTitle] = useState('');
    const [description, setDescription] = useState('');
    const [priority, setPriority] = useState('normal');
    const [taskType, setTaskType] = useState('execution');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [focusedField, setFocusedField] = useState<string | null>(null);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setError(null);

        try {
            await onConfirm({ title, description, priority, task_type: taskType });
            onClose();
        } catch (err: any) {
            setError(err.message || 'Failed to create task');
        } finally {
            setIsLoading(false);
        }
    };

    const getPriorityColor = (p: string) => {
        const map: Record<string, string> = {
            low: 'blue',
            normal: 'emerald',
            urgent: 'orange',
            critical: 'rose'
        };
        return map[p] || 'blue';
    };

    const selectedPriority = PRIORITY_OPTIONS.find(p => p.value === priority);
    const selectedType = TYPE_OPTIONS.find(t => t.value === taskType);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            {/* Backdrop with blur */}
            <div 
                className="absolute inset-0 bg-black/60 dark:bg-black/70 backdrop-blur-sm transition-opacity duration-200"
                onClick={onClose}
            />
            
            <div className="relative w-full max-w-lg max-h-[90vh] overflow-hidden rounded-2xl border border-gray-200 dark:border-[#1e2535] bg-white dark:bg-[#161b27] shadow-2xl dark:shadow-[0_25px_50px_-12px_rgba(0,0,0,0.5)] transition-colors duration-200">
                
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-5 border-b border-gray-100 dark:border-[#1e2535] bg-gray-50/50 dark:bg-[#0f1117]/50">
                    <div className="flex items-center gap-3">
                        <div className="p-2 rounded-xl bg-blue-100 dark:bg-blue-500/10 text-blue-600 dark:text-blue-400">
                            <FileText className="w-5 h-5" />
                        </div>
                        <div>
                            <h2 className="text-lg font-bold text-gray-900 dark:text-white">
                                Create New Task
                            </h2>
                            <p className="text-xs text-gray-500 dark:text-gray-400">
                                Assign work to your AI workforce
                            </p>
                        </div>
                    </div>
                    <button aria-label="Close" 
                        onClick={onClose}
                        className="p-2 rounded-lg text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-[#1e2535] transition-all duration-150"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="p-6 space-y-5 overflow-y-auto max-h-[calc(90vh-80px)]">
                    
                    {/* Title Field */}
                    <div className="space-y-1.5">
                        <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300">
                            Task Title
                        </label>
                        <div className={`
                            relative rounded-xl border transition-all duration-200
                            ${focusedField === 'title' 
                                ? 'border-blue-500 ring-4 ring-blue-500/10 dark:ring-blue-500/20' 
                                : 'border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347]'
                            }
                        `}>
                            <input
                                type="text"
                                value={title}
                                onChange={(e) => setTitle(e.target.value)}
                                onFocus={() => setFocusedField('title')}
                                onBlur={() => setFocusedField(null)}
                                className="w-full bg-transparent px-4 py-3 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none rounded-xl"
                                placeholder="e.g., Analyze Q4 market trends"
                                required
                            />
                            {title && (
                                <div className="absolute right-3 top-1/2 -translate-y-1/2">
                                    <Sparkles className="w-4 h-4 text-blue-500/50" />
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Description Field */}
                    <div className="space-y-1.5">
                        <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300">
                            Description
                        </label>
                        <div className={`
                            relative rounded-xl border transition-all duration-200
                            ${focusedField === 'desc' 
                                ? 'border-blue-500 ring-4 ring-blue-500/10 dark:ring-blue-500/20' 
                                : 'border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347]'
                            }
                        `}>
                            <textarea
                                value={description}
                                onChange={(e) => setDescription(e.target.value)}
                                onFocus={() => setFocusedField('desc')}
                                onBlur={() => setFocusedField(null)}
                                rows={4}
                                className="w-full bg-transparent px-4 py-3 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none rounded-xl resize-none"
                                placeholder="Describe what needs to be done in detail..."
                                required
                            />
                        </div>
                    </div>

                    {/* Priority Selection - Visual Cards */}
                    <div className="space-y-1.5">
                        <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300">
                            Priority Level
                        </label>
                        <div className="grid grid-cols-2 gap-2">
                            {PRIORITY_OPTIONS.map((option) => {
                                const isSelected = priority === option.value;
                                const color = option.color;
                                return (
                                    <button
                                        key={option.value}
                                        type="button"
                                        onClick={() => setPriority(option.value)}
                                        className={`
                                            relative p-3 rounded-xl border text-left transition-all duration-200
                                            ${isSelected 
                                                ? `bg-${color}-50 dark:bg-${color}-500/10 border-${color}-300 dark:border-${color}-500/30 ring-1 ring-${color}-500/20` 
                                                : 'bg-white dark:bg-[#0f1117] border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347]'
                                            }
                                        `}
                                    >
                                        <div className="flex items-center gap-2">
                                            <div className={`
                                                w-2 h-2 rounded-full bg-${color}-500 
                                                ${isSelected ? 'scale-125' : 'scale-100'} transition-transform duration-200
                                            `} />
                                            <span className={`
                                                text-sm font-semibold
                                                ${isSelected ? `text-${color}-700 dark:text-${color}-300` : 'text-gray-700 dark:text-gray-300'}
                                            `}>
                                                {option.label}
                                            </span>
                                        </div>
                                        <p className={`
                                            text-xs mt-1 
                                            ${isSelected ? `text-${color}-600/70 dark:text-${color}-400/70` : 'text-gray-500 dark:text-gray-500'}
                                        `}>
                                            {option.description}
                                        </p>
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    {/* Task Type Selection */}
                    <div className="space-y-1.5">
                        <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300">
                            Task Type
                        </label>
                        <div className="grid grid-cols-3 gap-2">
                            {TYPE_OPTIONS.map((option) => {
                                const isSelected = taskType === option.value;
                                return (
                                    <button
                                        key={option.value}
                                        type="button"
                                        onClick={() => setTaskType(option.value)}
                                        className={`
                                            relative p-3 rounded-xl border text-center transition-all duration-200
                                            ${isSelected 
                                                ? 'bg-blue-50 dark:bg-blue-500/10 border-blue-300 dark:border-blue-500/30 ring-1 ring-blue-500/20' 
                                                : 'bg-white dark:bg-[#0f1117] border-gray-200 dark:border-[#1e2535] hover:border-gray-300 dark:hover:border-[#2a3347]'
                                            }
                                        `}
                                    >
                                        <div className="text-xl mb-1">{option.icon}</div>
                                        <div className={`
                                            text-xs font-semibold
                                            ${isSelected ? 'text-blue-700 dark:text-blue-300' : 'text-gray-700 dark:text-gray-300'}
                                        `}>
                                            {option.label}
                                        </div>
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    {/* Error Message */}
                    {error && (
                        <div className="flex items-start gap-2 p-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-red-700 dark:text-red-300 text-sm">
                            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                            <span>{error}</span>
                        </div>
                    )}

                    {/* Footer Actions */}
                    <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-100 dark:border-[#1e2535]">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-5 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-[#1e2535] rounded-xl transition-all duration-150"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={isLoading || !title.trim() || !description.trim()}
                            className={`
                                flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-semibold text-white
                                bg-blue-600 hover:bg-blue-500 dark:bg-blue-600 dark:hover:bg-blue-500
                                disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-blue-600
                                shadow-lg shadow-blue-500/25 dark:shadow-blue-500/20
                                transition-all duration-150
                            `}
                        >
                            {isLoading ? (
                                <>
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                    Creating...
                                </>
                            ) : (
                                <>
                                    Create Task
                                </>
                            )}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
};
