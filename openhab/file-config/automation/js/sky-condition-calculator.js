// Staged file-provider equivalent of managed rule sky-condition-calculator.
// Do not install while the REST-managed rule exists: that would duplicate the writer.
const { rules, triggers, items } = require('openhab');

rules.JSRule({
  id: 'sky-condition-calculator',
  name: 'Calculate Sky Condition',
  triggers: [
    triggers.ItemStateChangeTrigger('Sun_SunPhaseName'),
    triggers.ItemStateChangeTrigger('Sun_TotalRadiation'),
    triggers.ItemStateChangeTrigger('AmbientWeatherWS2902A_SolarRadiation'),
    triggers.ItemStateChangeTrigger('WeatherData_HealthStatus'),
    triggers.GenericCronTrigger('0 0/2 * * * ?'),
  ],
  execute: () => {
    // Sky condition calculator with explicit weather freshness.
    function safeState(itemName, fallback) {
      try {
        const s = String(items.getItem(itemName).state);
        if (s === '' || s === 'NULL' || s === 'UNDEF') return fallback;
        return s;
      } catch (e) {
        return fallback;
      }
    }

    function asNumber(itemName) {
      const s = safeState(itemName, '');
      const cleaned = s.replace(/[^0-9.+-]/g, '');
      if (cleaned === '' || cleaned === '+' || cleaned === '-' || cleaned === '.' || cleaned === '+.' || cleaned === '-.') return NaN;
      const n = Number(cleaned);
      return Number.isFinite(n) ? n : NaN;
    }

    function token(value) {
      return String(value || '').trim().toUpperCase().replace(/[\s-]+/g, '_');
    }

    function postIfExists(itemName, value) {
      try {
        items.getItem(itemName).postUpdate(String(value));
      } catch (e) {
        // Diagnostic Items may be unavailable during reload.
      }
    }

    const sunPhase = token(safeState('Sun_SunPhaseName', 'UNKNOWN'));
    const theoretical = asNumber('Sun_TotalRadiation');
    const actual = asNumber('AmbientWeatherWS2902A_SolarRadiation');
    const weatherStatus = token(safeState('WeatherData_HealthStatus', 'UNKNOWN'));
    const weatherAge = asNumber('WeatherData_WH65B_AgeSeconds');
    // DEGRADED means some add-on sensor (e.g. the WH31E shade sensor) is
    // quiet — the WH65B station that feeds solar radiation is validated by
    // its own age check below, so don't let an unrelated sensor blind us
    // (2026-07-14: silent WH31E flipped SkyCondition to STALE needlessly).
    const weatherFresh = (weatherStatus === 'OK' || weatherStatus === 'DEGRADED') && Number.isFinite(weatherAge) && weatherAge <= 180;

    let condition = 'UNKNOWN';
    let icon = 'iconify:mdi:help-circle';
    let reason = 'unknown';
    let ratio = NaN;

    if (sunPhase === 'NIGHT') {
      condition = 'NIGHT';
      icon = safeState('MoonPhaseicon', 'iconify:mdi:weather-night');
      reason = 'night';
    } else if (!weatherFresh) {
      condition = 'STALE';
      icon = 'iconify:mdi:cloud-alert';
      reason = 'weather_stale';
    } else if (!Number.isFinite(theoretical)) {
      condition = 'STALE';
      icon = 'iconify:mdi:cloud-alert';
      reason = 'theoretical_invalid';
    } else if (theoretical > 20) {
      if (!Number.isFinite(actual)) {
        condition = 'STALE';
        icon = 'iconify:mdi:cloud-alert';
        reason = 'actual_invalid';
      } else {
        ratio = Math.max(0, actual) / theoretical;
        if (ratio < 0.3) {
          condition = 'OVERCAST';
          icon = 'iconify:bi:clouds-fill';
        } else if (ratio < 0.7) {
          condition = 'PARTLY_CLOUDY';
          icon = 'iconify:bi:cloud-sun-fill';
        } else {
          condition = 'CLEAR';
          icon = safeState('SunPhaseIcon', 'iconify:mdi:white-balance-sunny');
        }
        reason = 'ratio';
      }
    } else {
      condition = 'TWILIGHT';
      icon = safeState('SunPhaseIcon', 'iconify:mdi:weather-sunset');
      reason = 'low_theoretical';
    }

    const previousCondition = safeState('SkyCondition', 'NULL');
    const previousIcon = safeState('SkyConditionIcon', 'NULL');
    if (previousCondition !== condition) items.getItem('SkyCondition').postUpdate(condition);
    if (previousIcon !== icon) items.getItem('SkyConditionIcon').postUpdate(icon);

    // Rate-limit diagnostic posts so jdbc everyChange persistence is not flooded:
    // LastEval gets a 60s floor, Diagnostic posts on state-key change or with LastEval.
    let evalDue = true;
    const prevEval = safeState('SkyCondition_LastEval', '');
    if (prevEval) {
      const prevMs = Date.parse(prevEval);
      if (Number.isFinite(prevMs) && (Date.now() - prevMs) < 60000) evalDue = false;
    }
    if (evalDue) postIfExists('SkyCondition_LastEval', new Date().toISOString());
    const diagKey = condition + '|' + reason + '|' + weatherFresh;
    const prevDiag = safeState('SkyCondition_Diagnostic', '');
    const pm = prevDiag.match(/condition=([^,]*),reason=([^,]*)/);
    const pf = prevDiag.match(/weatherFresh=([^,]*)/);
    const prevKey = (pm ? pm[1] + '|' + pm[2] : '') + '|' + (pf ? pf[1] : '');
    if (evalDue || diagKey !== prevKey) postIfExists(
      'SkyCondition_Diagnostic',
      'condition=' + condition +
        ',reason=' + reason +
        ',weatherStatus=' + weatherStatus +
        ',weatherAgeSec=' + (Number.isFinite(weatherAge) ? weatherAge.toFixed(0) : 'missing') +
        ',weatherFresh=' + weatherFresh +
        ',actual=' + (Number.isFinite(actual) ? actual.toFixed(0) : 'missing') +
        ',theoretical=' + (Number.isFinite(theoretical) ? theoretical.toFixed(0) : 'missing') +
        ',ratio=' + (Number.isFinite(ratio) ? ratio.toFixed(2) : 'n/a')
    );

    if (previousCondition !== condition || previousIcon !== icon) {
      console.info('SkyCondition updated: ' + condition + ' (' + icon + '), reason=' + reason);
    } else {
      console.debug('SkyCondition unchanged: ' + condition + ', reason=' + reason);
    }
  },
});
