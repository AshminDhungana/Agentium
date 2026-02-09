import React, { useEffect, useState } from 'react';
import { constitutionService } from '@/services/constitution';
import { toast } from 'react-hot-toast';
import { BookOpen, AlertTriangle, Save, RotateCcw, Check, X, Clock, Shield } from 'lucide-react';

const DEFAULT_CONSTITUTION = {
    id: '',
    version: 'v1.0.0',
    version_number: 1,
    preamble: 'We the Sovereign...',
    articles: {
        'article_1': { title: 'Default', content: 'Default content' }
    },
    prohibited_actions: [],
    sovereign_preferences: { transparency: 'high' },
    effective_date: new Date().toISOString(),
    created_by: 'system',
    is_active: true
};

export function ConstitutionPage() {
    const [constitution, setConstitution] = useState<any>(DEFAULT_CONSTITUTION);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isEditing, setIsEditing] = useState(false);
    const [editedConstitution, setEditedConstitution] = useState<any>(DEFAULT_CONSTITUTION);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        loadConstitution();
    }, []);

    const loadConstitution = async () => {
        try {
            setLoading(true);
            setError(null);
            const data = await constitutionService.getCurrentConstitution();

            // Deep merge to ensure all nested objects exist
            const safeData = {
                ...DEFAULT_CONSTITUTION,
                ...data,
                articles: data?.articles || DEFAULT_CONSTITUTION.articles,
                prohibited_actions: Array.isArray(data?.prohibited_actions)
                    ? data.prohibited_actions
                    : (typeof data?.prohibited_actions === 'string'
                        ? [data.prohibited_actions]
                        : DEFAULT_CONSTITUTION.prohibited_actions),
                sovereign_preferences: {
                    ...DEFAULT_CONSTITUTION.sovereign_preferences,
                    ...(data?.sovereign_preferences || {})
                }
            };

            setConstitution(safeData);
            setEditedConstitution(JSON.parse(JSON.stringify(safeData)));
        } catch (err: any) {
            console.error('Failed to load:', err);
            const errorMsg = err.response?.data?.detail || err.message || 'Failed to load constitution';
            setError(errorMsg);
            toast.error('Failed to load constitution');

            setConstitution(DEFAULT_CONSTITUTION);
            setEditedConstitution(JSON.parse(JSON.stringify(DEFAULT_CONSTITUTION)));
        } finally {
            setLoading(false);
        }
    };

    const handleSave = async () => {
        try {
            setSaving(true);

            if (!editedConstitution.preamble?.trim()) {
                toast.error('Preamble cannot be empty');
                return;
            }

            await constitutionService.updateConstitution({
                preamble: editedConstitution.preamble,
                articles: editedConstitution.articles,
                prohibited_actions: Array.isArray(editedConstitution.prohibited_actions)
                    ? editedConstitution.prohibited_actions
                    : [],
                sovereign_preferences: editedConstitution.sovereign_preferences
            });

            toast.success('Constitution updated successfully');
            setIsEditing(false);
            await loadConstitution();
        } catch (err: any) {
            toast.error(err.response?.data?.detail || 'Update failed');
        } finally {
            setSaving(false);
        }
    };

    const handleReset = () => {
        setEditedConstitution(JSON.parse(JSON.stringify(constitution)));
        setIsEditing(false);
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
                    <p className="text-gray-600">Loading Constitution...</p>
                </div>
            </div>
        );
    }

    const data = isEditing ? (editedConstitution || DEFAULT_CONSTITUTION) : (constitution || DEFAULT_CONSTITUTION);

    if (!data || !data.prohibited_actions) {
        return (
            <div className="p-6 text-center">
                <AlertTriangle className="h-12 w-12 text-yellow-500 mx-auto mb-4" />
                <h2 className="text-xl font-semibold mb-2">Error Loading Constitution</h2>
                <p className="text-gray-600 mb-4">{error || 'Unknown error occurred'}</p>
                <button
                    onClick={loadConstitution}
                    className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
                >
                    Retry
                </button>
            </div>
        );
    }

    return (
        <div className="max-w-5xl mx-auto p-6 space-y-6">
            {/* Header */}
            <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg p-6 shadow-sm">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <div className="bg-blue-600 p-3 rounded-lg">
                            <Shield className="h-8 w-8 text-white" />
                        </div>
                        <div>
                            <h1 className="text-3xl font-bold text-gray-900">The Constitution</h1>
                            <div className="flex items-center gap-3 mt-1">
                                <span className="text-sm text-gray-600">Version {data.version}</span>
                                <span className="text-gray-400">•</span>
                                <span className="text-sm text-gray-600 flex items-center gap-1">
                                    <Clock className="h-3 w-3" />
                                    {new Date(data.effective_date).toLocaleDateString()}
                                </span>
                                {data.is_active && (
                                    <>
                                        <span className="text-gray-400">•</span>
                                        <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-100 text-green-800 text-xs font-medium rounded-full">
                                            <Check className="h-3 w-3" />
                                            Active
                                        </span>
                                    </>
                                )}
                            </div>
                        </div>
                    </div>

                    <div className="flex gap-2">
                        {isEditing ? (
                            <>
                                <button
                                    onClick={handleReset}
                                    className="px-4 py-2 text-gray-700 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors flex items-center gap-2"
                                    disabled={saving}
                                >
                                    <X className="h-4 w-4" />
                                    Cancel
                                </button>
                                <button
                                    onClick={handleSave}
                                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2 disabled:opacity-50"
                                    disabled={saving}
                                >
                                    {saving ? (
                                        <>
                                            <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                                            Saving...
                                        </>
                                    ) : (
                                        <>
                                            <Save className="h-4 w-4" />
                                            Save Changes
                                        </>
                                    )}
                                </button>
                            </>
                        ) : (
                            <button
                                onClick={() => setIsEditing(true)}
                                className="px-4 py-2 border-2 border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 hover:border-gray-400 transition-colors"
                            >
                                Edit Constitution
                            </button>
                        )}
                    </div>
                </div>
            </div>

            {error && (
                <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded">
                    <div className="flex items-center gap-2">
                        <AlertTriangle className="h-5 w-5 text-red-500" />
                        <p className="text-red-700">{error}</p>
                    </div>
                </div>
            )}

            {/* Preamble */}
            <section className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
                    <BookOpen className="h-5 w-5 text-blue-600" />
                    Preamble
                </h2>
                {isEditing ? (
                    <textarea
                        value={data.preamble || ''}
                        onChange={(e) => setEditedConstitution({
                            ...editedConstitution,
                            preamble: e.target.value
                        })}
                        className="w-full h-32 p-4 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none font-serif"
                        placeholder="Enter the preamble..."
                    />
                ) : (
                    <p className="text-gray-700 leading-relaxed font-serif italic border-l-4 border-blue-600 pl-4">
                        {data.preamble}
                    </p>
                )}
            </section>

            {/* Articles */}
            <section className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                <h2 className="text-xl font-semibold mb-4">Articles</h2>
                <div className="space-y-4">
                    {data.articles && Object.entries(data.articles).map(([key, article]: [string, any], index) => (
                        <div key={key} className="border-l-4 border-indigo-500 pl-4 py-2 hover:bg-gray-50 rounded-r transition-colors">
                            <h3 className="font-semibold text-gray-900 mb-2">
                                Article {index + 1}: {article?.title || 'Untitled'}
                            </h3>
                            {isEditing ? (
                                <textarea
                                    value={article?.content || ''}
                                    onChange={(e) => {
                                        const newArticles = {
                                            ...editedConstitution.articles,
                                            [key]: { ...article, content: e.target.value }
                                        };
                                        setEditedConstitution({ ...editedConstitution, articles: newArticles });
                                    }}
                                    className="w-full mt-2 p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                                    rows={3}
                                />
                            ) : (
                                <p className="text-gray-600 leading-relaxed">{article?.content}</p>
                            )}
                        </div>
                    ))}
                </div>
            </section>

            {/* Prohibited Actions */}
            <section className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
                    <AlertTriangle className="h-5 w-5 text-red-600" />
                    Prohibited Actions
                </h2>
                {isEditing ? (
                    <div>
                        <textarea
                            value={Array.isArray(data.prohibited_actions)
                                ? data.prohibited_actions.join('\n')
                                : ''}
                            onChange={(e) => setEditedConstitution({
                                ...editedConstitution,
                                prohibited_actions: e.target.value
                                    .split('\n')
                                    .map(line => line.trim())
                                    .filter(line => line.length > 0)
                            })}
                            className="w-full h-32 p-4 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 focus:border-transparent resize-none font-mono text-sm"
                            placeholder="One action per line..."
                        />
                        <p className="text-sm text-gray-500 mt-2">Enter one prohibited action per line</p>
                    </div>
                ) : (
                    <ul className="space-y-2">
                        {Array.isArray(data.prohibited_actions) && data.prohibited_actions.length > 0 ? (
                            data.prohibited_actions.map((action: string, idx: number) => (
                                <li key={idx} className="flex items-start gap-3 p-3 bg-red-50 rounded-lg">
                                    <X className="h-5 w-5 text-red-500 mt-0.5 flex-shrink-0" />
                                    <span className="text-gray-800">{action}</span>
                                </li>
                            ))
                        ) : (
                            <li className="text-gray-400 italic p-3 bg-gray-50 rounded-lg">
                                No prohibited actions defined
                            </li>
                        )}
                    </ul>
                )}
            </section>

            {/* Sovereign Preferences */}
            <section className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                <h2 className="text-xl font-semibold mb-4">Sovereign Preferences</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {data.sovereign_preferences && Object.entries(data.sovereign_preferences).map(([key, value]: [string, any]) => (
                        <div key={key} className="bg-gradient-to-br from-gray-50 to-gray-100 rounded-lg p-4 border border-gray-200">
                            <label className="text-sm font-medium text-gray-600 capitalize block mb-2">
                                {key.replace(/_/g, ' ')}
                            </label>
                            {isEditing ? (
                                <input
                                    type="text"
                                    value={String(value ?? '')}
                                    onChange={(e) => {
                                        const newPrefs = {
                                            ...editedConstitution.sovereign_preferences,
                                            [key]: e.target.value
                                        };
                                        setEditedConstitution({ ...editedConstitution, sovereign_preferences: newPrefs });
                                    }}
                                    className="w-full p-2 border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                />
                            ) : (
                                <p className="text-gray-900 font-medium">{String(value ?? 'N/A')}</p>
                            )}
                        </div>
                    ))}
                </div>
            </section>

            {/* Footer Info */}
            <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-600 border border-gray-200">
                <p>
                    Created by: <span className="font-medium">{data.created_by || 'System'}</span>
                    {' • '}
                    Last updated: <span className="font-medium">{new Date(data.effective_date).toLocaleString()}</span>
                </p>
            </div>
        </div>
    );
}