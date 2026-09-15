import React from 'react';
import { useRightSidebar } from '../../components/layout/RightSidebar';
import { ConversationList } from './ConversationList';
import styles from './ConversationSidebar.module.css';

export const ConversationSidebar: React.FC = () => {
    const { isCollapsed, toggleCollapse } = useRightSidebar();

    return (
        <div className={`${styles.sidebar} ${isCollapsed ? styles.collapsed : ''}`}>
            <div className={styles.header}>
                <h2 className={styles.title}>Conversations</h2>
                <button
                    className={styles.collapseBtn}
                    onClick={toggleCollapse}
                    aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                    aria-expanded={!isCollapsed}
                >
                    {isCollapsed ? '›' : '‹'}
                </button>
            </div>
            <ConversationList />
        </div>
    );
};