// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { holdAction, HOLD_DURATION_MS } from '../src/lib/actions/holdAction.js';

function pointer(type, pointerId) {
  const event = new Event(type, { bubbles: true, cancelable: true });
  Object.defineProperty(event, 'pointerId', { value: pointerId });
  return event;
}

function key(type, value, options = {}) {
  return new KeyboardEvent(type, {
    key: value,
    bubbles: true,
    cancelable: true,
    ...options,
  });
}

async function settle() {
  await Promise.resolve();
  await Promise.resolve();
}

describe('holdAction', () => {
  let node;
  let submit;
  let phases;
  let action;

  beforeEach(() => {
    vi.useFakeTimers();
    node = document.createElement('button');
    document.body.append(node);
    submit = vi.fn().mockResolvedValue({ status: 'accepted' });
    phases = [];
    action = holdAction(node, {
      contractKey: 'circadian:OFF:enabled',
      onSubmit: submit,
      onPhaseChange: (phase) => phases.push(phase),
    });
  });

  afterEach(() => {
    action?.destroy();
    node?.remove();
    vi.useRealTimers();
  });

  it('requires a full accessible 600 ms pointer hold and awaits exactly one submission', async () => {
    expect(HOLD_DURATION_MS).toBe(600);
    node.dispatchEvent(pointer('pointerdown', 1));
    vi.advanceTimersByTime(599);
    expect(submit).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1);
    expect(submit).toHaveBeenCalledTimes(1);
    await settle();
    expect(phases).toEqual(expect.arrayContaining(['holding', 'pending', 'accepted']));

    node.dispatchEvent(pointer('pointerup', 1));
    vi.advanceTimersByTime(600);
    expect(submit).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['pointerup', () => pointer('pointerup', 1)],
    ['pointercancel', () => pointer('pointercancel', 1)],
    ['pointerleave', () => pointer('pointerleave', 1)],
    ['blur', () => new FocusEvent('blur')],
  ])('cancels on early %s', (_name, eventFactory) => {
    node.dispatchEvent(pointer('pointerdown', 1));
    vi.advanceTimersByTime(300);
    node.dispatchEvent(eventFactory());
    vi.advanceTimersByTime(400);

    expect(submit).not.toHaveBeenCalled();
    expect(phases.at(-1)).toBe('confirmed');
  });

  it('cancels an unfinished hold when destroyed', () => {
    node.dispatchEvent(pointer('pointerdown', 1));
    vi.advanceTimersByTime(300);
    action.destroy();
    vi.advanceTimersByTime(400);

    expect(submit).not.toHaveBeenCalled();
  });

  it('supports Enter and Space while ignoring repeats', async () => {
    node.dispatchEvent(key('keydown', 'Enter', { repeat: true }));
    vi.advanceTimersByTime(600);
    expect(submit).not.toHaveBeenCalled();

    node.dispatchEvent(key('keydown', 'Enter'));
    vi.advanceTimersByTime(600);
    await settle();
    expect(submit).toHaveBeenCalledTimes(1);

    node.dispatchEvent(key('keyup', 'Enter'));
    node.dispatchEvent(key('keydown', ' '));
    vi.advanceTimersByTime(600);
    await settle();
    expect(submit).toHaveBeenCalledTimes(2);
  });

  it('cancels a keyboard hold on early release', () => {
    node.dispatchEvent(key('keydown', ' '));
    vi.advanceTimersByTime(300);
    node.dispatchEvent(key('keyup', ' '));
    vi.advanceTimersByTime(400);

    expect(submit).not.toHaveBeenCalled();
  });

  it('cancels an unfinished hold when any second pointer arrives', async () => {
    node.dispatchEvent(pointer('pointerdown', 11));
    vi.advanceTimersByTime(250);
    node.dispatchEvent(pointer('pointerdown', 22));
    node.dispatchEvent(pointer('pointerup', 22));
    vi.advanceTimersByTime(350);
    await settle();

    expect(submit).not.toHaveBeenCalled();
    expect(phases.at(-1)).toBe('confirmed');
  });

  it('cancels an unfinished hold when its semantic contract changes', () => {
    node.dispatchEvent(pointer('pointerdown', 1));
    vi.advanceTimersByTime(300);
    action.update({
      contractKey: 'circadian:ON:enabled',
      onSubmit: submit,
      onPhaseChange: (phase) => phases.push(phase),
    });
    vi.advanceTimersByTime(400);

    expect(submit).not.toHaveBeenCalled();
    expect(phases.at(-1)).toBe('confirmed');
  });

  it('cancels an unfinished hold when its submission callback changes', () => {
    const replacementSubmit = vi.fn().mockResolvedValue({ status: 'accepted' });
    node.dispatchEvent(pointer('pointerdown', 1));
    vi.advanceTimersByTime(300);
    action.update({
      contractKey: 'circadian:OFF:enabled',
      onSubmit: replacementSubmit,
      onPhaseChange: (phase) => phases.push(phase),
    });
    vi.advanceTimersByTime(400);

    expect(submit).not.toHaveBeenCalled();
    expect(replacementSubmit).not.toHaveBeenCalled();
    expect(phases.at(-1)).toBe('confirmed');
  });

  it('keeps an unfinished hold only for an exact same action contract update', async () => {
    node.dispatchEvent(pointer('pointerdown', 1));
    vi.advanceTimersByTime(300);
    action.update({
      contractKey: 'circadian:OFF:enabled',
      onSubmit: submit,
      onPhaseChange: (phase) => phases.push(phase),
    });
    vi.advanceTimersByTime(300);
    await settle();

    expect(submit).toHaveBeenCalledTimes(1);
  });

  it('blocks all new holds while the awaited submission is pending', async () => {
    let resolve;
    submit.mockReturnValue(new Promise((done) => { resolve = done; }));
    node.dispatchEvent(pointer('pointerdown', 1));
    vi.advanceTimersByTime(600);
    expect(submit).toHaveBeenCalledTimes(1);

    node.dispatchEvent(pointer('pointerdown', 2));
    node.dispatchEvent(key('keydown', 'Enter'));
    vi.advanceTimersByTime(1_200);
    expect(submit).toHaveBeenCalledTimes(1);

    resolve({ status: 'accepted' });
    await settle();
    expect(phases.at(-1)).toBe('accepted');
  });

  it('presents accepted, error, and outcome-unknown distinctly without retrying', async () => {
    action.destroy();

    for (const [result, terminal] of [
      [{ status: 'accepted' }, 'accepted'],
      [Promise.reject(new Error('denied')), 'error'],
      [{ status: 'unknown' }, 'unknown'],
    ]) {
      phases.length = 0;
      submit = vi.fn().mockReturnValue(result);
      action = holdAction(node, {
        onSubmit: submit,
        onPhaseChange: (phase) => phases.push(phase),
      });
      node.dispatchEvent(pointer('pointerdown', 1));
      vi.advanceTimersByTime(600);
      await settle();
      vi.advanceTimersByTime(5_000);

      expect(submit).toHaveBeenCalledTimes(1);
      expect(phases.at(-1)).toBe(terminal);
      action.destroy();
    }
  });

  it('cancels when an update disables the action', () => {
    node.dispatchEvent(pointer('pointerdown', 1));
    vi.advanceTimersByTime(300);
    action.update({
      disabled: true,
      onSubmit: submit,
      onPhaseChange: (phase) => phases.push(phase),
    });
    vi.advanceTimersByTime(400);

    expect(submit).not.toHaveBeenCalled();
    expect(phases.at(-1)).toBe('unavailable');
  });
});
