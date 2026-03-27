import type { ReactNode } from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

export function SortableItem({ id, children }: { id: string; children: ReactNode }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id });

  return (
    <div
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
      }}
      className={`cursor-grab select-none rounded-xl transition-shadow duration-200
        ${isDragging
          ? 'opacity-60 shadow-2xl scale-[1.02] ring-2 ring-honeywell-red/30 z-50 cursor-grabbing'
          : 'hover:shadow-lg active:shadow-2xl active:scale-[1.01] active:cursor-grabbing'
        }`}
    >
      {children}
    </div>
  );
}
