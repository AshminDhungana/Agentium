import React, { useState } from 'react';
import { useChatStore } from '../../store/chatStore';
import type { Conversation } from '../../store/chatStore';
import { formatDistanceToNow } from 'date-fns';
import styles from './ConversationList.module.css';

interface ConversationItemProps {
    conversation: Conversation;
    isActive: boolean;
    isCollapsed: boolean;
    onSelect: (id: string) => void;
    onRename: (id: string, title: string) => void;
    onArchive: (id: string) => void;
    onDelete: (id: string) => void;
}

const ConversationItem: React.FC<ConversationItemProps> = ({
    conversation,
    isActive,
    isCollapsed,
    onSelect,
    onRename,
    onArchive,
    onDelete,
}) => {
    const [showActions, setShowActions] = useState(false);
    const [isRenaming, setIsRenaming] = useState(false);
    const [renameValue, setRenameValue] = useState(conversation.title);

    const handleRename = () => {
        onRename(conversation.id, renameValue);
        setIsRenaming(false);
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') handleRename();
        if (e.key === 'Escape') setIsRenaming(false);
    };

    if (isCollapsed) {
        return (
            <button
                data-testid="conversation-item"
                className={`${styles.item} ${styles.collapsed} ${isActive ? styles.active : ''}`}
                onClick={() => onSelect(conversation.id)}
                title={conversation.title}
                aria-label={conversation.title}
                role="option"
                aria-selected={isActive}
            >
                <span className={styles.icon}>💬</span>
                {conversation.is_archived && <span className={styles.archiveBadge} aria-label="Archived">📦</span>}
            </button>
        );
    }

    return (
        <div
            data-testid="conversation-item"
            className={`${styles.item} ${isActive ? styles.active : ''}`}
            onMouseEnter={() => setShowActions(true)}
            onMouseLeave={() => setShowActions(false)}
        >
            <button
                className={styles.mainButton}
                onClick={() => onSelect(conversation.id)}
                role="option"
                aria-selected={isActive}
                aria-label={conversation.title}
            >
                <span className={styles.icon}>💬</span>
                <div className={styles.textContent}>
                    {isRenaming ? (
                        <input
                            type="text"
                            value={renameValue}
                            onChange={e => setRenameValue(e.target.value)}
                            onBlur={handleRename}
                            onKeyDown={handleKeyDown}
                            autoFocus
                            className={styles.renameInput}
                            aria-label="Conversation title"
                        />
                    ) : (
                        <span className={styles.title}>{conversation.title}</span>
                    )}
                    <div className={styles.meta}>
                        <span className={styles.preview}>{conversation.last_message_preview}</span>
                        <span className={styles.time}>
                            {conversation.updated_at ? formatDistanceToNow(new Date(conversation.updated_at), { addSuffix: true }) : ''}
                        </span>
                    </div>
                </div>
                {conversation.is_archived && <span className={styles.archiveBadge} aria-label="Archived">📦</span>}
            </button>
            <div className={`${styles.actions} ${showActions ? styles.visible : ''}`}>
                <button
                    className={styles.actionBtn}
                    onClick={e => { e.stopPropagation(); setIsRenaming(true); }}
                    aria-label="Rename conversation"
                >
                    ✏️
                </button>
                <button
                    className={styles.actionBtn}
                    onClick={e => { e.stopPropagation(); onArchive(conversation.id); }}
                    aria-label={conversation.is_archived ? 'Unarchive' : 'Archive'}
                >
                    {conversation.is_archived ? '📤' : '📦'}
                </button>
                <button
                    className={styles.actionBtn}
                    onClick={e => { e.stopPropagation(); onDelete(conversation.id); }}
                    aria-label="Delete conversation"
                >
                    🗑️
                </button>
            </div>
        </div>
    );
};

export const ConversationList: React.FC = () => {
    const {
        conversations,
        currentConversationId,
        setConversation,
        createConversation,
        deleteConversation,
        updateConversation,
        sidebarWidth,
    } = useChatStore();

    const isCollapsed = sidebarWidth <= 48;

    const handleCreate = async () => {
        const title = prompt('Conversation title:', 'New Conversation');
        if (title) {
            await createConversation(title);
        }
    };

    const handleRename = async (id: string, title: string) => {
        if (title.trim() && title !== conversations.find(c => c.id === id)?.title) {
            await updateConversation(id, { title: title.trim() });
        }
    };

    const handleArchive = async (id: string) => {
        const conv = conversations.find(c => c.id === id);
        if (conv) await updateConversation(id, { is_archived: !conv.is_archived });
    };

    const handleDelete = async (id: string) => {
        if (confirm('Delete this conversation?')) {
            await deleteConversation(id);
        }
    };

    return (
        <div className={styles.container} role="listbox" aria-label="Conversations">
            <button
                className={styles.newButton}
                onClick={handleCreate}
                aria-label="New conversation"
                disabled={isCollapsed}
            >
                <span className={styles.newIcon}>+</span>
                {!isCollapsed && <span className={styles.newLabel}>New Conversation</span>}
            </button>
            <div className={styles.list}>
                {conversations.length === 0 ? (
                    <div className={styles.empty} role="status">
                        {!isCollapsed && 'No conversations yet. Create one to get started!'}
                    </div>
                ) : (
                    conversations.map(conv => (
                        <ConversationItem
                            key={conv.id}
                            conversation={conv}
                            isActive={conv.id === currentConversationId}
                            isCollapsed={isCollapsed}
                            onSelect={setConversation}
                            onRename={handleRename}
                            onArchive={handleArchive}
                            onDelete={handleDelete}
                        />
                    ))
                )}
            </div>
        </div>
    );
};