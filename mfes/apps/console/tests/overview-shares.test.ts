import { describe, expect, it } from 'vitest';
import { isPositive, shareOf } from '../app/lib/overview-shares';

describe('shareOf', () => {
  it('divides exactly and returns a 0–1 fraction', () => {
    // exact to four places, which is far finer than the whole percent a meter prints
    expect(shareOf('1500.0000', '3500.0000')).toBe(0.4286);
    expect(shareOf('1.0000', '4.0000')).toBe(0.25);
    expect(shareOf('3500.0000', '3500.0000')).toBe(1);
  });

  it('never exceeds a whole, and gives nothing for a part that is not positive', () => {
    expect(shareOf('5.0000', '4.0000')).toBe(1);
    expect(shareOf('0.0000', '4.0000')).toBe(0);
    expect(shareOf('-2.0000', '4.0000')).toBe(0);
  });

  it('gives nothing when there is no usable whole or either figure is unreadable', () => {
    expect(shareOf('1.0000', '0.0000')).toBe(0);
    expect(shareOf('1.0000', '-4.0000')).toBe(0);
    expect(shareOf('n/a', '4.0000')).toBe(0);
    expect(shareOf('1.0000', '')).toBe(0);
  });

  it('stays exact on figures near the storage limit, where a float would drift', () => {
    expect(shareOf('999999999999999.0000', '999999999999999.0000')).toBe(1);
    expect(shareOf('499999999999999.5000', '999999999999999.0000')).toBe(0.5);
    // a share too small for four places is no share at all, never a rounding artefact
    expect(shareOf('0.0001', '1000000000000.0000')).toBe(0);
  });
});

describe('isPositive', () => {
  it('is true only for a readable amount above zero', () => {
    expect(isPositive('0.0001')).toBe(true);
    expect(isPositive('0.0000')).toBe(false);
    expect(isPositive('-1.0000')).toBe(false);
    expect(isPositive('x')).toBe(false);
  });
});
