import {createRecommendationState} from '../household/recommendationState.js';
import {loadProductionWeather} from '../household/observationClient.js';
// Mounted only in expanded production details. Last subscriber aborts transport.
const production=createRecommendationState({load:loadProductionWeather});
export const productionWeatherRaw=production.raw;
export const productionWeatherClock=production.clock;
