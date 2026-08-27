export function createLatestRefreshCoordinator() {
  let generation = 0;
  let controller = null;
  let destroyed = false;

  return {
    async run(load, commit) {
      if (destroyed) return false;
      controller?.abort();
      const currentController = new AbortController();
      controller = currentController;
      const currentGeneration = ++generation;
      const isCurrent = () => (
        !destroyed
        && !currentController.signal.aborted
        && currentGeneration === generation
      );

      try {
        const value = await load(currentController.signal);
        if (!isCurrent()) return false;
        commit(value);
        return true;
      } catch (error) {
        if (!isCurrent()) return false;
        throw error;
      } finally {
        if (controller === currentController) controller = null;
      }
    },
    destroy() {
      destroyed = true;
      generation += 1;
      controller?.abort();
      controller = null;
    },
  };
}
