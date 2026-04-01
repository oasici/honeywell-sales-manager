import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Input } from '../../components/ui/Input';

describe('Input', () => {
  it('renders with label', () => {
    const { container } = render(
      <Input label="Email" placeholder="ornek@test.com" />,
    );
    expect(container.firstChild).toMatchSnapshot();
  });

  it('renders with helper text', () => {
    const { container } = render(
      <Input label="Sifre" type="password" helperText="En az 8 karakter" />,
    );
    expect(container.firstChild).toMatchSnapshot();
  });

  it('renders with error state', () => {
    const { container } = render(
      <Input label="Email" error="Gecersiz email adresi" />,
    );
    expect(container.firstChild).toMatchSnapshot();
  });

  it('renders without label', () => {
    const { container } = render(
      <Input placeholder="Ara..." />,
    );
    expect(container.firstChild).toMatchSnapshot();
  });
});
