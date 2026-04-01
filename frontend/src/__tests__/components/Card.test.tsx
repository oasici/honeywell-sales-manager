import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Card } from '../../components/ui/Card';

describe('Card', () => {
  it('renders with title', () => {
    const { container } = render(
      <Card title="Test Basligi">
        <p>Icerik</p>
      </Card>,
    );
    expect(container.firstChild).toMatchSnapshot();
  });

  it('renders without title', () => {
    const { container } = render(
      <Card>
        <p>Sadece icerik</p>
      </Card>,
    );
    expect(container.firstChild).toMatchSnapshot();
  });

  it('renders with title and action', () => {
    const { container } = render(
      <Card title="Ayarlar" action={<button>Kaydet</button>}>
        <p>Form alanlari</p>
      </Card>,
    );
    expect(container.firstChild).toMatchSnapshot();
  });
});
