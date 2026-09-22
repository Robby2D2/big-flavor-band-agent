import { describe, expect, it } from 'vitest';
import { NAV_DESTINATIONS, visibleDestinations } from '@/lib/navDestinations';

const labels = (role: Parameters<typeof visibleDestinations>[0]) =>
  visibleDestinations(role).map((destination) => destination.label);

describe('visibleDestinations', () => {
  it('gives a listener only the ungated destinations', () => {
    expect(labels('listener')).toEqual(['Search', 'Radio']);
  });

  it('treats a signed-out visitor like a listener', () => {
    expect(labels(undefined)).toEqual(['Search', 'Radio']);
  });

  it('adds Edit and Produce for an editor, but not Admin', () => {
    expect(labels('editor')).toEqual(['Search', 'Radio', 'Edit', 'Produce']);
  });

  it('gives an admin every destination', () => {
    expect(labels('admin')).toEqual(['Search', 'Radio', 'Edit', 'Produce', 'Admin']);
  });

  // The point of the shared list is that the two navs cannot drift, which only
  // holds while every gated destination declares its requirement here.
  it('gates exactly the produce/edit/admin routes', () => {
    const gated = NAV_DESTINATIONS.filter((destination) => destination.requires);

    expect(gated.map((destination) => [destination.href, destination.requires])).toEqual([
      ['/edit', 'edit'],
      ['/produce', 'edit'],
      ['/admin', 'admin'],
    ]);
  });
});
