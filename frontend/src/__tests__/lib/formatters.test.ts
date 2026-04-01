import { describe, it, expect } from 'vitest';
import { formatCurrency, formatPercent, formatNumber } from '../../lib/formatters';

describe('formatCurrency', () => {
  it('formats USD correctly', () => {
    expect(formatCurrency(1234.56, 'USD')).toMatchInlineSnapshot(`"$1.234,56"`);
  });

  it('formats TRY correctly', () => {
    expect(formatCurrency(1234.56, 'TRY')).toMatchInlineSnapshot(`"₺1.234,56"`);
  });

  it('formats EUR correctly', () => {
    expect(formatCurrency(1234.56, 'EUR')).toMatchInlineSnapshot(`"€1.234,56"`);
  });

  it('handles null/undefined with fallback to 0', () => {
    expect(formatCurrency(null)).toMatchInlineSnapshot(`"$0,00"`);
    expect(formatCurrency(undefined)).toMatchInlineSnapshot(`"$0,00"`);
  });

  it('handles zero', () => {
    expect(formatCurrency(0, 'USD')).toMatchInlineSnapshot(`"$0,00"`);
  });
});

describe('formatPercent', () => {
  it('formats percentage', () => {
    expect(formatPercent(75.5)).toMatchInlineSnapshot(`"%75,5"`);
  });
});

describe('formatNumber', () => {
  it('formats with Turkish grouping', () => {
    expect(formatNumber(1234567)).toMatchInlineSnapshot(`"1.234.567"`);
  });
});
