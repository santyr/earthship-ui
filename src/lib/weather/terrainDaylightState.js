import {createRecommendationState} from '../household/recommendationState.js';
import {loadTerrainDaylight} from '../household/observationClient.js';
const shared=createRecommendationState({load:loadTerrainDaylight});
export const terrainDaylightRaw=shared.raw;
export const terrainDaylightClock=shared.clock;
