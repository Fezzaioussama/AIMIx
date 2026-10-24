import { AmbientBackdrop } from '../../core/ui/AmbientBackdrop';
import { AboutSection } from './AboutSection';
import { FaqSection } from './FaqSection';
import { FinalCta } from './FinalCta';
import { Hero } from './Hero';
import { LandingFooter } from './LandingFooter';
import { LandingNav } from './LandingNav';
import { PlatformSection } from './PlatformSection';
import { ProcessSection } from './ProcessSection';
import { ScrollProgress } from './ScrollProgress';
import { SecuritySection } from './SecuritySection';
import { TechMarquee } from './TechMarquee';
import { ToolsSection } from './ToolsSection';
import { UseCasesSection } from './UseCasesSection';

/** The public front page at `/`: what AIMIx is, how it works, and where to start. */
export function LandingPage() {
  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[70] focus:rounded-lg focus:bg-slate-900 focus:px-4 focus:py-2 focus:text-white"
      >
        Skip to content
      </a>
      <AmbientBackdrop />
      <ScrollProgress />
      <LandingNav />
      {/* Clip, don't scroll: sections that slide in sideways start outside the viewport,
          and on a phone that would widen the page before they are revealed. */}
      <main id="main" className="overflow-x-clip">
        <Hero />
        <TechMarquee />
        <AboutSection />
        <PlatformSection />
        <ProcessSection />
        <UseCasesSection />
        <ToolsSection />
        <SecuritySection />
        <FaqSection />
        <FinalCta />
      </main>
      <LandingFooter />
    </>
  );
}
