import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MobileNav from '@/components/MobileNav';
import { visibleDestinations } from '@/lib/navDestinations';

const renderFor = (role: Parameters<typeof visibleDestinations>[0]) =>
  render(<MobileNav destinations={visibleDestinations(role)} />);

const toggle = () => screen.getByRole('button', { name: 'Menu' });

describe('MobileNav', () => {
  it('starts closed and opens on the toggle', async () => {
    const user = userEvent.setup();
    renderFor('listener');

    expect(screen.queryByRole('link', { name: 'Search' })).not.toBeInTheDocument();
    expect(toggle()).toHaveAttribute('aria-expanded', 'false');

    await user.click(toggle());

    expect(screen.getByRole('link', { name: 'Search' })).toBeInTheDocument();
    expect(toggle()).toHaveAttribute('aria-expanded', 'true');
  });

  it('closes again on the toggle', async () => {
    const user = userEvent.setup();
    renderFor('listener');

    await user.click(toggle());
    await user.click(toggle());

    expect(screen.queryByRole('link', { name: 'Search' })).not.toBeInTheDocument();
  });

  it('closes when a destination is tapped, so it does not persist across navigation', async () => {
    const user = userEvent.setup();
    renderFor('listener');

    await user.click(toggle());
    await user.click(screen.getByRole('link', { name: 'Radio' }));

    expect(screen.queryByRole('link', { name: 'Radio' })).not.toBeInTheDocument();
  });

  it('closes on Escape', async () => {
    const user = userEvent.setup();
    renderFor('listener');

    await user.click(toggle());
    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByRole('link', { name: 'Search' })).not.toBeInTheDocument();
  });

  // Hiding a gated link would still ship it to a listener's browser; the spec
  // asks for it to be absent, so assert on the DOM rather than on styling.
  it('puts no gated link in a listener\'s DOM at all', async () => {
    const user = userEvent.setup();
    renderFor('listener');

    await user.click(toggle());

    expect(screen.getByRole('link', { name: 'Search' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Radio' })).toBeInTheDocument();
    for (const gated of ['Edit', 'Produce', 'Admin']) {
      expect(screen.queryByRole('link', { name: gated })).not.toBeInTheDocument();
    }
  });

  it('shows Edit and Produce to an editor, but not Admin', async () => {
    const user = userEvent.setup();
    renderFor('editor');

    await user.click(toggle());

    expect(screen.getByRole('link', { name: 'Edit' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Produce' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Admin' })).not.toBeInTheDocument();
  });

  it('shows an admin every destination', async () => {
    const user = userEvent.setup();
    renderFor('admin');

    await user.click(toggle());

    for (const label of ['Search', 'Radio', 'Edit', 'Produce', 'Admin']) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument();
    }
  });
});
