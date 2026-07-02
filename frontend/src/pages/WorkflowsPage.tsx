import React from 'react';
import { WorkflowAutomationPanel } from '@/components/workflows/WorkflowAutomationPanel';

export const WorkflowsPage: React.FC = () => {
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-[#0f1117] p-4 md:p-6">
      <div className="max-w-7xl mx-auto">
        <WorkflowAutomationPanel />
      </div>
    </div>
  );
};

export default WorkflowsPage;
