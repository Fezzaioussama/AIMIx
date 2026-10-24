import { ActivePill } from '../../core/ui/ActivePill';

interface CategoryFilterProps {
  categories: string[];
  value: string;
  onChange: (category: string) => void;
}

const chipClass = (active: boolean) =>
  [
    'relative isolate rounded-full border px-4 py-1.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400',
    active
      ? 'border-sky-400/40 text-sky-100'
      : 'border-white/10 text-slate-300 hover:border-white/25 hover:text-white',
  ].join(' ');

/** Toggle chips that filter the gallery; the highlight glides to the chosen one. */
export function CategoryFilter({ categories, value, onChange }: CategoryFilterProps) {
  return (
    <div role="group" aria-label="Filter by category" className="mb-6 flex flex-wrap gap-2">
      {categories.map((category) => {
        const active = category === value;
        return (
          <button
            key={category}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(category)}
            className={chipClass(active)}
          >
            {active && <ActivePill layoutId="template-category" className="bg-sky-400/15" />}
            {category}
          </button>
        );
      })}
    </div>
  );
}
