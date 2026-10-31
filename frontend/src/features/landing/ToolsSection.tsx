import { AnimatedContent } from '../../core/ui/reactbits/AnimatedContent';
import { SpotlightCard } from '../../core/ui/reactbits/SpotlightCard';
import { TOOLS } from './content/solutions';
import { LandingSection } from './LandingSection';

const KIND_STYLE = {
  'Built-in': 'border-sky-400/30 bg-sky-400/10 text-sky-200',
  MCP: 'border-purple-400/30 bg-purple-400/10 text-purple-200',
} as const;

export function ToolsSection() {
  return (
    <LandingSection
      id="tools"
      eyebrow="Tools"
      title="Give every agent the right tools"
      description="Research the web, calculate, work with the files you uploaded and save artifacts. Connect an MCP server when you need more."
    >
      {/* Flex, not grid: five cards leave a short last row, and it should sit centred. */}
      <ul className="flex flex-wrap justify-center gap-4">
        {TOOLS.map((tool, index) => (
          <li
            key={tool.name}
            className="w-full sm:w-[calc(50%-0.5rem)] lg:w-[calc(33.333%-0.75rem)]"
          >
            <AnimatedContent whenInView delay={(index % 3) * 0.08} className="h-full">
              <SpotlightCard className="h-full p-6 transition-transform duration-300 hover:-translate-y-1">
                <div className="flex items-start justify-between gap-3">
                  <span className="grid size-11 place-items-center rounded-xl bg-white/[0.06] text-sky-200 ring-1 ring-white/10">
                    <tool.icon aria-hidden="true" className="size-5" />
                  </span>
                  <span
                    className={`rounded-full border px-2.5 py-0.5 text-[0.7rem] font-semibold ${KIND_STYLE[tool.kind]}`}
                  >
                    {tool.kind}
                  </span>
                </div>
                <h3 className="mt-5 text-lg font-bold text-white">{tool.name}</h3>
                <p className="mt-1.5 text-sm text-slate-400">{tool.detail}</p>
              </SpotlightCard>
            </AnimatedContent>
          </li>
        ))}
      </ul>
    </LandingSection>
  );
}
