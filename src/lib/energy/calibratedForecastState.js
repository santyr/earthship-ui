import { createRecommendationState } from '../household/recommendationState.js';
import { loadCalibratedEnergy } from '../household/observationClient.js';
const shared = createRecommendationState({ load: loadCalibratedEnergy });
export const calibratedForecastRaw = shared.raw;
