import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Announcer } from './Announcer';

const liveRegions = () => document.body.querySelectorAll(':scope > [role="status"]');

describe('Announcer', () => {
  it('is one polite, atomic status line straight under the body, empty at first', () => {
    render(
      <div hidden>
        <Announcer message="" />
      </div>,
    );

    const regions = liveRegions();
    expect(regions).toHaveLength(1);
    expect(regions[0]).toHaveAttribute('aria-live', 'polite');
    expect(regions[0]).toHaveAttribute('aria-atomic', 'true');
    expect(regions[0]).toHaveClass('sr-only');
    expect(regions[0]).toBeEmptyDOMElement();
  });

  it('says each new message, even while its owner is hidden', () => {
    const { rerender } = render(
      <div hidden>
        <Announcer message="" />
      </div>,
    );

    rerender(
      <div hidden>
        <Announcer message="Draft ready." />
      </div>,
    );

    expect(liveRegions()[0]).toHaveTextContent('Draft ready.');
    expect(liveRegions()[0].closest('[hidden]')).toBeNull();
  });

  it('leaves with its owner', () => {
    const { unmount } = render(<Announcer message="Draft ready." />);

    unmount();

    expect(liveRegions()).toHaveLength(0);
  });
});
