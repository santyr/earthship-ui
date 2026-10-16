import { describe,it,expect } from 'vitest';
import { parseUpdateEvidenceSSEMessage } from '../src/lib/openhab/sse.js';

describe('native Astro SSE evidence', () => {
  it('carries upstream state and generation for unchanged native values', () => {
    const raw = JSON.stringify({ topic:'openhab/items/Sun_TimeLeft/stateupdated',payload:JSON.stringify({value:'1 d',lastStateUpdate:1791820799574}) });
    expect(parseUpdateEvidenceSSEMessage(raw)).toEqual({name:'Sun_TimeLeft',lastStateUpdate:1791820799574,state:'1 d'});
  });
});
