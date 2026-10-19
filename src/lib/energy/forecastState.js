import { createRecommendationState } from '../household/recommendationState.js';
import { loadEnergyObservation } from '../household/observationClient.js';
// Reuse the bounded, subscriber-owned GET transport and cleanup policy.
const shared = createRecommendationState({ load: loadEnergyObservation });
export const energyForecastRaw = shared.raw;
export const energyForecastClock = shared.clock;
