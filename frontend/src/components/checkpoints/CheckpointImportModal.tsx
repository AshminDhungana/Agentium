/**
 * CheckpointImportModal — Phase 7
 * Modal for importing checkpoints with validation and conflict resolution.
 */

import React, { useState, useCallback } from 'react';
import { showToast } from '@/hooks/useToast';
import {
    Upload,
    FileJson,
    AlertCircle,
    CheckCircle2,
    X,
    ShieldCheck,
    GitBranch,
    AlertTriangle,
    FileCheck,
    Download,
} from 'lucide-react';
import {
    checkpointsService,
    ValidationResult,
    ImportResult,
    ImportOptions,
} from '../../services/checkpoints';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';

// ─── Conflict Resolution Options ─────────────────────────────────────────────

const CONFLICT_OPTIONS: Array<{
    value: ImportOptions['conflictResolution'];
    label: string;
    description: string;
}> = [
    {
        value: 'skip',
        label: 'Skip Conflicts',
        description: 'Skip importing checkpoints that conflict with existing ones',
    },
    {
        value: 'replace',
        label: 'Replace Existing',
        description: 'Overwrite existing checkpoints with imported data',
    },
    {
        value: 'rename',
        label: 'Auto-Rename',
        description: 'Append suffix to create unique IDs and branch names',
    },
    {
        value: 'merge',
        label: 'Smart Merge',
        description: 'Merge agent states and keep latest artifacts',
    },
];

// ─── Props ───────────────────────────────────────────────────────────────────

interface CheckpointImportModalProps {
    isOpen: boolean;
    onClose: () => void;
    onImportSuccess: (result: ImportResult) => void;
}

// ─── Component ─────────────────────────────────────────────────────────────

export const CheckpointImportModal: React.FC<CheckpointImportModalProps> = ({
    isOpen,
    onClose,
    onImportSuccess,
}) => {
    const [file, setFile] = useState<File | null>(null);
    const [isDragging, setIsDragging] = useState(false);
    const [isValidating, setIsValidating] = useState(false);
    const [isImporting, setIsImporting] = useState(false);
    const [validation, setValidation] = useState<ValidationResult | null>(null);
    const [importResult, setImportResult] = useState<ImportResult | null>(null);
    const [options, setOptions] = useState<ImportOptions>({
        targetBranch: '',
        skipValidation: false,
        conflictResolution: 'rename',
    });
    const [step, setStep] = useState<'upload' | 'validate' | 'resolve' | 'complete'>('upload');

    // ─── File Handling ───────────────────────────────────────────────────────

    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(true);
    }, []);

    const handleDragLeave = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
    }, []);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        
        const droppedFile = e.dataTransfer.files[0];
        if (droppedFile && droppedFile.name.endsWith('.json')) {
            setFile(droppedFile);
            setStep('validate');
            validateFile(droppedFile);
        } else {
            showToast.error('Please upload a valid JSON file');
        }
    }, []);

    const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        const selectedFile = e.target.files?.[0];
        if (selectedFile) {
            if (selectedFile.name.endsWith('.json')) {
                setFile(selectedFile);
                setStep('validate');
                validateFile(selectedFile);
            } else {
                showToast.error('Please upload a valid JSON file');
            }
        }
    }, []);

    // ─── Validation ──────────────────────────────────────────────────────────

    const validateFile = async (fileToValidate: File) => {
        setIsValidating(true);
        try {
            const result = await checkpointsService.validateCheckpoint(fileToValidate);
            setValidation(result);
            
            if (result.valid) {
                showToast.success('Checkpoint validation passed');
            } else {
                showToast.error(`Validation failed: ${result.errors.join(', ')}`);
            }
        } catch (err: any) {
            showToast.error(err?.response?.data?.detail || 'Validation failed');
        } finally {
            setIsValidating(false);
        }
    };

    // ─── Import ──────────────────────────────────────────────────────────────

    const handleImport = async () => {
        if (!file) return;
        
        setIsImporting(true);
        try {
            const result = await checkpointsService.importCheckpoint(file, options);
            setImportResult(result);
            
            if (result.success) {
                showToast.success('Checkpoint imported successfully');
                setStep('complete');
                onImportSuccess(result);
            } else {
                showToast.error('Import completed with conflicts');
                setStep('resolve');
            }
        } catch (err: any) {
            showToast.error(err?.response?.data?.detail || 'Import failed');
        } finally {
            setIsImporting(false);
        }
    };

    // ─── Reset ───────────────────────────────────────────────────────────────

    const handleReset = () => {
        setFile(null);
        setValidation(null);
        setImportResult(null);
        setStep('upload');
        setOptions({
            targetBranch: '',
            skipValidation: false,
            conflictResolution: 'rename',
        });
    };

    // ─── Render ──────────────────────────────────────────────────────────────

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
            <div className="bg-white dark:bg-[#161b27] rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 dark:border-[#1e2535]">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                            <Upload className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                        </div>
                        <div>
                            <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100">
                                Import Checkpoint
                            </h3>
                            <p className="text-sm text-slate-500 dark:text-slate-400">
                                Restore from backup or shared checkpoint
                            </p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-[#1e2535] rounded-lg transition-colors"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-auto p-6">
                    {/* Step 1: Upload */}
                    {step === 'upload' && (
                        <div className="space-y-4">
                            <div
                                onDragOver={handleDragOver}
                                onDragLeave={handleDragLeave}
                                onDrop={handleDrop}
                                className={`
                                    border-2 border-dashed rounded-xl p-8 text-center transition-all duration-200
                                    ${isDragging
                                        ? 'border-blue-500 bg-blue-50 dark:bg-blue-500/10'
                                        : 'border-slate-300 dark:border-slate-600 hover:border-slate-400 dark:hover:border-slate-500'
                                    }
                                `}
                            >
                                <div className="w-16 h-16 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center mx-auto mb-4">
                                    <FileJson className="w-8 h-8 text-slate-400" />
                                </div>
                                <p className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                                    Drop checkpoint JSON file here
                                </p>
                                <p className="text-xs text-slate-500 dark:text-slate-500 mb-4">
                                    or click to browse files
                                </p>
                                <input
                                    type="file"
                                    accept=".json,application/json"
                                    onChange={handleFileSelect}
                                    className="hidden"
                                    id="checkpoint-file-input"
                                />
                                <label
                                    htmlFor="checkpoint-file-input"
                                    className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg cursor-pointer transition-colors"
                                >
                                    <Upload className="w-4 h-4" />
                                    Select File
                                </label>
                            </div>

                            <div className="bg-slate-50 dark:bg-slate-800/50 rounded-lg p-4">
                                <h4 className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider mb-2">
                                    Supported Formats
                                </h4>
                                <ul className="text-xs text-slate-500 dark:text-slate-400 space-y-1">
                                    <li>• Agentium checkpoint export (.json)</li>
                                    <li>• Includes task state, agent states, and artifacts</li>
                                    <li>• Integrity checksum validation</li>
                                </ul>
                            </div>
                        </div>
                    )}

                    {/* Step 2: Validation */}
                    {(step === 'validate' || step === 'resolve') && validation && (
                        <div className="space-y-4">
                            {/* File info */}
                            <div className="flex items-center gap-3 p-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg">
                                <FileCheck className="w-5 h-5 text-slate-400" />
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm font-medium text-slate-700 dark:text-slate-300 truncate">
                                        {file?.name}
                                    </p>
                                    <p className="text-xs text-slate-500">
                                        {(file?.size ? (file.size / 1024).toFixed(1) : 0)} KB
                                    </p>
                                </div>
                                <button
                                    onClick={handleReset}
                                    className="text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
                                >
                                    Change
                                </button>
                            </div>

                            {/* Validation status */}
                            <div className={`
                                rounded-lg p-4 border
                                ${validation.valid
                                    ? 'bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20'
                                    : 'bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/20'
                                }
                            `}>
                                <div className="flex items-center gap-2 mb-3">
                                    {validation.valid ? (
                                        <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                                    ) : (
                                        <AlertCircle className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                                    )}
                                    <span className={`
                                        font-medium
                                        ${validation.valid
                                            ? 'text-emerald-700 dark:text-emerald-300'
                                            : 'text-amber-700 dark:text-amber-300'
                                        }
                                    `}>
                                        {validation.valid ? 'Validation Passed' : 'Validation Issues Found'}
                                    </span>
                                </div>

                                {validation.errors.length > 0 && (
                                    <div className="mb-3">
                                        <p className="text-xs font-medium text-red-600 dark:text-red-400 mb-1">Errors:</p>
                                        <ul className="text-xs text-red-600 dark:text-red-400 space-y-1">
                                            {validation.errors.map((err, i) => (
                                                <li key={i}>• {err}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}

                                {validation.warnings.length > 0 && (
                                    <div>
                                        <p className="text-xs font-medium text-amber-600 dark:text-amber-400 mb-1">Warnings:</p>
                                        <ul className="text-xs text-amber-600 dark:text-amber-400 space-y-1">
                                            {validation.warnings.map((warn, i) => (
                                                <li key={i}>• {warn}</li>
                                            ))}
                                        </ul>
                                    </div>
                                )}

                                <div className="mt-3 pt-3 border-t border-slate-200 dark:border-slate-700">
                                    <div className="flex items-center gap-4 text-xs">
                                        <span className="text-slate-500">
                                            Schema: <span className="font-mono text-slate-700 dark:text-slate-300">{validation.schema_version}</span>
                                        </span>
                                        <span className="text-slate-500">
                                            Checksum: {validation.checksum_valid ? (
                                                <span className="text-emerald-600 dark:text-emerald-400">Valid</span>
                                            ) : (
                                                <span className="text-red-600 dark:text-red-400">Invalid</span>
                                            )}
                                        </span>
                                    </div>
                                </div>
                            </div>

                            {/* Import Options */}
                            <div className="space-y-3">
                                <h4 className="text-sm font-medium text-slate-700 dark:text-slate-300">
                                    Import Options
                                </h4>

                                {/* Target Branch */}
                                <div>
                                    <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-1">
                                        Target Branch (optional)
                                    </label>
                                    <div className="flex items-center gap-2">
                                        <GitBranch className="w-4 h-4 text-slate-400" />
                                        <input
                                            type="text"
                                            value={options.targetBranch}
                                            onChange={(e) => setOptions({ ...options, targetBranch: e.target.value })}
                                            placeholder="e.g., imported-from-backup"
                                            className="flex-1 px-3 py-2 text-sm border border-slate-200 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100"
                                        />
                                    </div>
                                </div>

                                {/* Conflict Resolution */}
                                <div>
                                    <label className="block text-xs font-medium text-slate-600 dark:text-slate-400 mb-2">
                                        Conflict Resolution Strategy
                                    </label>
                                    <div className="space-y-2">
                                        {CONFLICT_OPTIONS.map((opt) => (
                                            <label
                                                key={opt.value}
                                                className={`
                                                    flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors
                                                    ${options.conflictResolution === opt.value
                                                        ? 'border-blue-500 bg-blue-50 dark:bg-blue-500/10'
                                                        : 'border-slate-200 dark:border-slate-600 hover:border-slate-300 dark:hover:border-slate-500'
                                                    }
                                                `}
                                            >
                                                <input
                                                    type="radio"
                                                    name="conflictResolution"
                                                    value={opt.value}
                                                    checked={options.conflictResolution === opt.value}
                                                    onChange={(e) => setOptions({ ...options, conflictResolution: e.target.value as ImportOptions['conflictResolution'] })}
                                                    className="mt-0.5"
                                                />
                                                <div>
                                                    <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
                                                        {opt.label}
                                                    </p>
                                                    <p className="text-xs text-slate-500 dark:text-slate-400">
                                                        {opt.description}
                                                    </p>
                                                </div>
                                            </label>
                                        ))}
                                    </div>
                                </div>

                                {/* Skip Validation Toggle */}
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={options.skipValidation}
                                        onChange={(e) => setOptions({ ...options, skipValidation: e.target.checked })}
                                        className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                                    />
                                    <span className="text-sm text-slate-600 dark:text-slate-400">
                                        Skip validation (not recommended)
                                    </span>
                                </label>
                            </div>

                            {/* Conflicts from previous attempt */}
                            {importResult?.conflicts && importResult.conflicts.length > 0 && (
                                <div className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 rounded-lg p-4">
                                    <div className="flex items-center gap-2 mb-3">
                                        <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400" />
                                        <span className="font-medium text-red-700 dark:text-red-300">
                                            Conflicts Detected
                                        </span>
                                    </div>
                                    <ul className="space-y-2">
                                        {importResult.conflicts.map((conflict, i) => (
                                            <li key={i} className="text-xs text-red-600 dark:text-red-400">
                                                <span className="font-medium">{conflict.type}:</span> {conflict.message}
                                                <br />
                                                <span className="text-slate-500">Resolution: {conflict.resolution}</span>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Step 3: Complete */}
                    {step === 'complete' && importResult?.success && (
                        <div className="text-center py-8">
                            <div className="w-16 h-16 rounded-full bg-emerald-100 dark:bg-emerald-500/20 flex items-center justify-center mx-auto mb-4">
                                <CheckCircle2 className="w-8 h-8 text-emerald-600 dark:text-emerald-400" />
                            </div>
                            <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-100 mb-2">
                                Import Successful
                            </h3>
                            <p className="text-sm text-slate-500 dark:text-slate-400">
                                Checkpoint has been successfully imported and is ready to use.
                            </p>
                            {importResult.checkpoint && (
                                <div className="mt-4 p-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg">
                                    <p className="text-xs text-slate-500">Checkpoint ID</p>
                                    <code className="text-sm font-mono text-slate-700 dark:text-slate-300">
                                        {importResult.checkpoint.id}
                                    </code>
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="flex items-center justify-between px-6 py-4 border-t border-slate-100 dark:border-[#1e2535] bg-slate-50 dark:bg-slate-800/30">
                    <div className="flex items-center gap-2">
                        {isValidating && (
                            <>
                                <LoadingSpinner size="sm" />
                                <span className="text-xs text-slate-500">Validating...</span>
                            </>
                        )}
                        {isImporting && (
                            <>
                                <LoadingSpinner size="sm" />
                                <span className="text-xs text-slate-500">Importing...</span>
                            </>
                        )}
                    </div>
                    <div className="flex items-center gap-3">
                        {step === 'upload' && (
                            <button
                                onClick={onClose}
                                className="px-4 py-2 text-sm font-medium text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 transition-colors"
                            >
                                Cancel
                            </button>
                        )}
                        {(step === 'validate' || step === 'resolve') && (
                            <>
                                <button
                                    onClick={handleReset}
                                    className="px-4 py-2 text-sm font-medium text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 transition-colors"
                                >
                                    Back
                                </button>
                                <button
                                    onClick={handleImport}
                                    disabled={isImporting || (!validation?.valid && !options.skipValidation)}
                                    className={`
                                        px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2
                                        ${(!validation?.valid && !options.skipValidation) || isImporting
                                            ? 'bg-slate-300 dark:bg-slate-600 cursor-not-allowed'
                                            : 'bg-blue-600 hover:bg-blue-700 text-white'
                                        }
                                    `}
                                >
                                    {isImporting ? (
                                        <>
                                            <LoadingSpinner size="sm" />
                                            Importing...
                                        </>
                                    ) : (
                                        <>
                                            <Download className="w-4 h-4" />
                                            Import Checkpoint
                                        </>
                                    )}
                                </button>
                            </>
                        )}
                        {step === 'complete' && (
                            <button
                                onClick={onClose}
                                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg"
                            >
                                Done
                            </button>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default CheckpointImportModal;