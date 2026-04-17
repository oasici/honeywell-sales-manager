import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Badge } from '../../components/ui/Badge';

describe('Badge', () => {
  it('renders default variant', () => {
    const { container } = render(<Badge>Default</Badge>);
    expect(container.firstChild).toMatchSnapshot();
  });

  it('renders success variant', () => {
    const { container } = render(<Badge variant="success">Onaylandı</Badge>);
    expect(container.firstChild).toMatchSnapshot();
  });

  it('renders danger variant', () => {
    const { container } = render(<Badge variant="danger">Reddedildi</Badge>);
    expect(container.firstChild).toMatchSnapshot();
  });

  it('renders warning variant', () => {
    const { container } = render(<Badge variant="warning">Beklemede</Badge>);
    expect(container.firstChild).toMatchSnapshot();
  });

  it('renders info variant', () => {
    const { container } = render(<Badge variant="info">Bilgi</Badge>);
    expect(container.firstChild).toMatchSnapshot();
  });
});
