import { Link } from 'react-router-dom';
import { WidgetCard } from './WidgetCard';
import { Cpu, ChevronRight, Users, ListTodo, Radio } from 'lucide-react';

const links = [
  { to: '/agents', label: 'Agents', icon: Users },
  { to: '/models', label: 'Models', icon: Cpu },
  { to: '/tasks', label: 'Tasks', icon: ListTodo },
  { to: '/channels', label: 'Channels', icon: Radio },
];

export function QuickActions() {
  return (
    <WidgetCard title="Quick Actions" icon={Cpu} aria-label="Quick actions">
      <nav className="p-2">
        <ul className="space-y-1">
          {links.map(({ to, label, icon: Icon }) => (
            <li key={to}>
              <Link
                to={to}
                className="group flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm text-gray-700 transition-colors duration-200 hover:bg-subtle dark:text-gray-300 dark:hover:bg-subtle"
              >
                <Icon className="h-4 w-4 text-gray-400 transition-colors duration-200 group-hover:text-brand dark:text-gray-500 dark:group-hover:text-brand" aria-hidden="true" />
                <span className="flex-1 font-medium">{label}</span>
                <ChevronRight className="h-4 w-4 text-gray-300 transition-colors duration-200 group-hover:text-brand dark:text-gray-600 dark:group-hover:text-brand" aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </WidgetCard>
  );
}
