import {createRecommendationState} from '../household/recommendationState.js';
import {loadWeatherRainShadow,loadWeatherMarginals} from '../household/observationClient.js';
const rain=createRecommendationState({load:loadWeatherRainShadow});
const marginal=createRecommendationState({load:loadWeatherMarginals});
export const rainShadowRaw=rain.raw;
export const marginalShadowRaw=marginal.raw;
export const forecastVerificationClock=rain.clock;
