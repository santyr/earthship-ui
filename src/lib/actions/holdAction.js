export const HOLD_DURATION_MS = 600;

const HOLD_KEYS = new Set(['Enter', ' ', 'Spacebar']);

function terminalPhase(result) {
  return result?.status === 'unknown' ? 'unknown' : 'accepted';
}

function isUnknownError(error) {
  return error?.outcomeUnknown === true || error?.code === 'OUTCOME_UNKNOWN';
}

function normalizeOptions(options = {}) {
  return { holdMs: HOLD_DURATION_MS, disabled: false, ...options };
}

function sameActionContract(left, right) {
  return left.disabled === right.disabled
    && left.holdMs === right.holdMs
    && left.contractKey === right.contractKey
    && left.onSubmit === right.onSubmit;
}

export function holdAction(node, initialOptions = {}) {
  let options = normalizeOptions(initialOptions);
  let timer = null;
  let active = null;
  let submitting = false;
  let destroyed = false;

  function emit(phase) {
    options.onPhaseChange?.(phase);
  }

  function restingPhase() {
    return options.disabled ? 'unavailable' : 'confirmed';
  }

  function clearHold({ announce = true } = {}) {
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
    if (!submitting) active = null;
    if (announce && !destroyed && !submitting) emit(restingPhase());
  }

  async function submitOnce() {
    timer = null;
    if (destroyed || options.disabled || submitting || !active) {
      clearHold();
      return;
    }

    submitting = true;
    emit('pending');
    try {
      const result = await options.onSubmit?.();
      if (!destroyed) emit(terminalPhase(result));
    } catch (error) {
      if (!destroyed) emit(isUnknownError(error) ? 'unknown' : 'error');
    } finally {
      submitting = false;
      active = null;
    }
  }

  function start(source) {
    if (destroyed || options.disabled || submitting || active) return false;
    active = source;
    emit('holding');
    timer = setTimeout(submitOnce, options.holdMs);
    return true;
  }

  function onPointerDown(event) {
    if (active && !submitting) {
      clearHold();
      event.preventDefault();
      return;
    }
    if (start({ type: 'pointer', id: event.pointerId })) {
      event.preventDefault();
    }
  }

  function stopPointer(event) {
    if (active?.type !== 'pointer' || active.id !== event.pointerId) return;
    if (!submitting) clearHold();
  }

  function onKeyDown(event) {
    if (!HOLD_KEYS.has(event.key) || event.repeat) return;
    if (start({ type: 'keyboard', key: event.key })) event.preventDefault();
  }

  function onKeyUp(event) {
    if (
      active?.type !== 'keyboard'
      || !HOLD_KEYS.has(event.key)
      || (active.key !== event.key && !(active.key === 'Spacebar' && event.key === ' '))
    ) return;
    if (!submitting) clearHold();
    event.preventDefault();
  }

  function onBlur() {
    if (!submitting) clearHold();
  }

  node.addEventListener('pointerdown', onPointerDown);
  node.addEventListener('pointerup', stopPointer);
  node.addEventListener('pointercancel', stopPointer);
  node.addEventListener('pointerleave', stopPointer);
  node.addEventListener('keydown', onKeyDown);
  node.addEventListener('keyup', onKeyUp);
  node.addEventListener('blur', onBlur);
  emit(restingPhase());

  return {
    update(nextOptions = {}) {
      const previous = options;
      const next = normalizeOptions(nextOptions);
      const invalidatesActiveHold = active && !submitting
        && !sameActionContract(previous, next);
      options = next;

      if (invalidatesActiveHold) {
        clearHold();
      } else if (options.disabled && !previous.disabled && !submitting) {
        emit('unavailable');
      }
    },
    destroy() {
      destroyed = true;
      clearHold({ announce: false });
      node.removeEventListener('pointerdown', onPointerDown);
      node.removeEventListener('pointerup', stopPointer);
      node.removeEventListener('pointercancel', stopPointer);
      node.removeEventListener('pointerleave', stopPointer);
      node.removeEventListener('keydown', onKeyDown);
      node.removeEventListener('keyup', onKeyUp);
      node.removeEventListener('blur', onBlur);
    },
  };
}
