import {createRecommendationState} from '../household/recommendationState.js';
import {loadWeatherCapabilities} from '../household/observationClient.js';
const shared=createRecommendationState({load:loadWeatherCapabilities});
export const weatherCapabilityRaw=shared.raw;
export const weatherCapabilityClock=shared.clock;
