import { describe, expect, it } from 'vitest';
import { compassPresentation } from '../src/lib/ui/compassPresentation.js';

describe('compassPresentation', () => {
  it.each([
    [0, 'N · 0°'],
    [22.5, 'NNE · 23°'],
    [78, 'ENE · 78°'],
    [180, 'S · 180°'],
    [270, 'W · 270°'],
    [348.75, 'N · 349°'],
    [360, 'N · 0°'],
    [-10, 'N · 350°'],
  ])('formats %s degrees as a sixteen-point heading', (degrees, headingText) => {
    expect(compassPresentation(degrees, 4).headingText).toBe(headingText);
  });

  it.each([null, undefined, '', 'NULL', 'UNDEF', 'north', Number.NaN])(
    'does not invent a direction for %s',
    (degrees) => {
      const result = compassPresentation(degrees, 4);
      expect(result.hasHeading).toBe(false);
      expect(result.heading).toBe(0);
      expect(result.point).toBe(null);
      expect(result.headingText).toBe('DIR —');
      expect(result.ariaLabel).toBe('Wind direction unavailable, speed 4 mph');
    }
  );

  it('treats zero speed as calm and suppresses the heading', () => {
    expect(compassPresentation(78, 0)).toEqual({
      hasHeading: false,
      heading: 0,
      point: null,
      headingText: 'CALM',
      hasSpeed: true,
      speedText: '0',
      calm: true,
      ariaLabel: 'Wind calm, speed 0 mph',
    });
  });

  it.each([null, undefined, '', 'NULL', 'UNDEF', 'fast', Number.NaN, -1])(
    'shows unavailable speed without corrupting a valid heading for %s',
    (speed) => {
      const result = compassPresentation(78, speed);
      expect(result.hasHeading).toBe(true);
      expect(result.headingText).toBe('ENE · 78°');
      expect(result.hasSpeed).toBe(false);
      expect(result.speedText).toBe('—');
      expect(result.ariaLabel).toBe('Wind direction ENE, 78 degrees, speed unavailable');
    }
  );
});
