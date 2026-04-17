import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Button } from '../../components/ui/Button';

describe('Button', () => {
  it('renders primary variant by default', () => {
    const { container } = render(<Button>Kaydet</Button>);
    expect(container.firstChild).toMatchSnapshot();
  });

  it('renders secondary variant', () => {
    const { container } = render(<Button variant="secondary">İptal</Button>);
    expect(container.firstChild).toMatchSnapshot();
  });

  it('renders danger variant', () => {
    const { container } = render(<Button variant="danger">Sil</Button>);
    expect(container.firstChild).toMatchSnapshot();
  });

  it('renders loading state with spinner', () => {
    const { container } = render(<Button loading>Yükleniyor</Button>);
    expect(container.firstChild).toMatchSnapshot();
  });

  it('renders disabled state', () => {
    const { container } = render(<Button disabled>Disabled</Button>);
    expect(container.firstChild).toMatchSnapshot();
  });

  it('renders small size', () => {
    const { container } = render(<Button size="sm">Small</Button>);
    expect(container.firstChild).toMatchSnapshot();
  });

  it('renders large size', () => {
    const { container } = render(<Button size="lg">Large</Button>);
    expect(container.firstChild).toMatchSnapshot();
  });
});
