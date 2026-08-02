import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// React Testing Library doesn't auto-clean under vitest's globals, so unmount
// between tests to keep queries from matching a previous test's DOM.
afterEach(() => {
  cleanup();
});
