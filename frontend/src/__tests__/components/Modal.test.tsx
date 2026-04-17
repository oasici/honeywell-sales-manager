import { render } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { Modal } from '../../components/ui/Modal';

describe('Modal', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <Modal isOpen={false} onClose={vi.fn()} title="Test">
        <p>İçerik</p>
      </Modal>,
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders with title and content when open', () => {
    const { container } = render(
      <Modal isOpen={true} onClose={vi.fn()} title="Email Detayi">
        <p>Email icerigi burada</p>
      </Modal>,
    );
    expect(container.firstChild).toMatchSnapshot();
  });

  it('renders large size', () => {
    const { container } = render(
      <Modal isOpen={true} onClose={vi.fn()} title="Buyuk Modal" size="lg">
        <p>Genis içerik</p>
      </Modal>,
    );
    expect(container.firstChild).toMatchSnapshot();
  });
});
