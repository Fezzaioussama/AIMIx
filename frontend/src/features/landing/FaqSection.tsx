import { ChevronDown } from 'lucide-react';
import { useId, useState } from 'react';

import { FAQ_ITEMS } from './content/solutions';
import type { FaqItem } from './content/solutions';
import { LandingSection } from './LandingSection';

interface FaqRowProps {
  item: FaqItem;
  open: boolean;
  onToggle: () => void;
}

/** One disclosure: a heading button over a panel that opens by animating its grid row. */
function FaqRow({ item, open, onToggle }: FaqRowProps) {
  const id = useId();
  return (
    <div className="border-b border-white/10">
      <h3>
        <button
          type="button"
          id={`${id}-button`}
          aria-expanded={open}
          aria-controls={`${id}-panel`}
          onClick={onToggle}
          className="flex w-full cursor-pointer items-center justify-between gap-4 py-5 text-left text-lg font-semibold text-white transition-colors hover:text-sky-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
        >
          {item.question}
          <ChevronDown
            aria-hidden="true"
            className={`size-5 shrink-0 text-slate-400 transition-transform duration-300 ${open ? 'rotate-180' : ''}`}
          />
        </button>
      </h3>
      {/* `inert` keeps the collapsed answer out of the tab order and the accessibility tree. */}
      <div
        id={`${id}-panel`}
        role="region"
        aria-labelledby={`${id}-button`}
        inert={!open}
        className={`grid transition-[grid-template-rows] duration-300 ${open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}
      >
        <div className="overflow-hidden">
          <p className="pb-5 text-slate-400">{item.answer}</p>
        </div>
      </div>
    </div>
  );
}

export function FaqSection() {
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  return (
    <LandingSection id="faq" eyebrow="FAQ" title="Questions, answered">
      <div className="mx-auto max-w-3xl border-t border-white/10">
        {FAQ_ITEMS.map((item, index) => (
          <FaqRow
            key={item.question}
            item={item}
            open={openIndex === index}
            onToggle={() => setOpenIndex(openIndex === index ? null : index)}
          />
        ))}
      </div>
    </LandingSection>
  );
}
