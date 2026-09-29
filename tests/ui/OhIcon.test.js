// @vitest-environment jsdom
// Common icons render from small offline collections; an unanticipated
// OpenHAB icon can still load the complete offline collection on demand.
import { cleanup, render, waitFor } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  `${process.cwd()}/node_modules/svelte/src/index-client.js`
));

import OhIcon, { iconCollectionsReady } from '../../src/lib/ui/OhIcon.svelte';

afterEach(cleanup);

describe('OhIcon', () => {
  it('renders an mdi icon once the async collections resolve', async () => {
    const { container } = render(OhIcon, {
      props: { icon: 'iconify:mdi:battery', size: '1rem' },
    });

    await iconCollectionsReady;
    await waitFor(() => expect(container.querySelector('svg')).not.toBeNull());
  });

  it('renders a bi icon from the second bundled collection', async () => {
    const { container } = render(OhIcon, {
      props: { icon: 'iconify:bi:cloud-sun-fill', size: '1rem' },
    });

    await iconCollectionsReady;
    await waitFor(() => expect(container.querySelector('svg')).not.toBeNull());
  });

  it('loads an unanticipated icon from its full offline collection', async () => {
    const { container } = render(OhIcon, {
      props: { icon: 'iconify:mdi:account', size: '1rem' },
    });
    await waitFor(() => expect(container.querySelector('svg')).not.toBeNull(), { timeout: 5000 });
  });

  it('renders nothing for NULL/UNDEF/missing icon states even after load', async () => {
    await iconCollectionsReady;
    for (const icon of [null, '', 'NULL', 'UNDEF']) {
      const { container } = render(OhIcon, { props: { icon } });
      expect(container.querySelector('svg')).toBeNull();
      cleanup();
    }
  });
});
