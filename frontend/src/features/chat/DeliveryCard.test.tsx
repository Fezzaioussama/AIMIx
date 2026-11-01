import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../../core/api/client';
import { confirmDelivery, deleteDelivery, getDelivery } from '../../core/api/deliveries';
import type { Delivery } from '../../core/api/deliveryTypes';
import { DeliveryCard } from './DeliveryCard';

vi.mock('../../core/api/deliveries', () => ({
  getDelivery: vi.fn(),
  confirmDelivery: vi.fn(),
  deleteDelivery: vi.fn(),
}));

const PENDING: Delivery = {
  id: 5,
  pipeline_id: 9,
  pipeline_name: 'News digest',
  destination: 'hooks.slack.com',
  hint: 'XyZ9',
  service: 'Slack',
  confirmed: false,
  enabled: true,
  last_sent_at: null,
  last_error: null,
};

beforeEach(() => {
  vi.mocked(getDelivery).mockReset();
  vi.mocked(confirmDelivery).mockReset();
  vi.mocked(deleteDelivery).mockReset();
});

describe('DeliveryCard', () => {
  it('sends nothing until the person confirms the address', async () => {
    vi.mocked(getDelivery).mockResolvedValue(PENDING);
    vi.mocked(confirmDelivery).mockResolvedValue({ ...PENDING, confirmed: true });
    render(<DeliveryCard deliveryId={5} />);

    expect(await screen.findByText('Results of News digest → Slack')).toBeInTheDocument();
    expect(screen.getByText('hooks.slack.com …XyZ9')).toBeInTheDocument();
    expect(screen.getByText(/Nothing is sent until you confirm/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    expect(confirmDelivery).toHaveBeenCalledWith(5);
    expect(await screen.findByText('Sending the results after every run')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument();
  });

  it('keeps the choice open when the address refuses the first message', async () => {
    vi.mocked(getDelivery).mockResolvedValue(PENDING);
    vi.mocked(confirmDelivery).mockImplementation(() =>
      Promise.reject(new ApiError('hooks.slack.com answered 404.', 502, 'delivery_failed')),
    );
    render(<DeliveryCard deliveryId={5} />);

    await userEvent.click(await screen.findByRole('button', { name: 'Confirm' }));

    expect(await screen.findByText('hooks.slack.com answered 404.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeEnabled();
  });

  it('can be cancelled instead', async () => {
    vi.mocked(getDelivery).mockResolvedValue(PENDING);
    vi.mocked(deleteDelivery).mockResolvedValue(undefined);
    render(<DeliveryCard deliveryId={5} />);

    await userEvent.click(await screen.findByRole('button', { name: 'Cancel' }));

    expect(deleteDelivery).toHaveBeenCalledWith(5);
    expect(await screen.findByText('Cancelled.')).toBeInTheDocument();
  });

  it('shows a delivery switched off as not sending', async () => {
    vi.mocked(getDelivery).mockResolvedValue({ ...PENDING, confirmed: true, enabled: false });
    render(<DeliveryCard deliveryId={5} />);

    expect(await screen.findByText(/Not sending/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument();
  });
});
