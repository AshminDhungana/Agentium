import re

with open('frontend/src/pages/ScalingDashboard.tsx', 'r') as f:
    content = f.read()

# Replace the opening: add mobile cards before table, wrap in Fragment
old_open = '''                ) : (
                    <div className="overflow-x-auto hidden md:block">'''

new_open = '''                ) : (
                    <>
                        {/* Mobile card view (below md) */}
                        <div className="md:hidden flex flex-col gap-3">
                            {history.map((event, i) => {
                                const levelCls = event.level?.toLowerCase() === 'info'
                                    ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300'
                                    : event.level?.toLowerCase() === 'warning'
                                    ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300'
                                    : 'bg-gray-100 text-gray-800 dark:bg-[#1e2535] dark:text-gray-300';
                                return (
                                    <div
                                        key={i}
                                        className="p-4 bg-gray-50 dark:bg-[#0f1117] rounded-lg border border-gray-100 dark:border-[#1e2535]"
                                    >
                                        <div className="flex items-center justify-between mb-2">
                                            <span className="text-xs text-gray-600 dark:text-gray-400">
                                                {new Date(event.created_at).toLocaleString()}
                                            </span>
                                            <span className={`px-2 py-0.5 rounded text-xs font-medium ${levelCls}`}>
                                                {event.level?.toUpperCase() || 'INFO'}
                                            </span>
                                        </div>
                                        <p className="text-sm font-medium text-gray-900 dark:text-white mb-1">{event.action}</p>
                                        <p className="text-xs text-gray-700 dark:text-gray-300">{event.description}</p>
                                    </div>
                                );
                            })}
                        </div>
                        {/* Desktop table (md and up) */}
                        <div className="overflow-x-auto hidden md:block">'''

# Replace the closing: add </> after </div> before )}
old_close = '''                    </div>
                )}'''

new_close = '''                    </div>
                    </>
                )}'''

content = content.replace(old_open, new_open)
content = content.replace(old_close, new_close, 1)

with open('frontend/src/pages/ScalingDashboard.tsx', 'w') as f:
    f.write(content)

print("Done.")
