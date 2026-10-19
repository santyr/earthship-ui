import { createRecommendationState } from '../household/recommendationState.js';
import { loadDailyPvPotential } from '../household/observationClient.js';
const shared=createRecommendationState({load:loadDailyPvPotential});
export const dailyPvRaw=shared.raw;
export const dailyPvClock=shared.clock;
