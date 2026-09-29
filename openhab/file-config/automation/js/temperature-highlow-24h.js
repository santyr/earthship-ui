// Staged file-provider equivalent of managed rule temp-highlow-24h.
// Do not install while the REST-managed rule exists: that would duplicate the writer.
const { rules, triggers, items } = require('openhab');

rules.JSRule({
  id: 'temp-highlow-24h',
  name: 'Update 24h temp high/low (indoor/outdoor)',
  triggers: [triggers.GenericCronTrigger('0 0/15 * * * ?')],
  execute: () => {
    var ZonedDateTime = Java.type('java.time.ZonedDateTime');
    var PersistenceExtensions = Java.type('org.openhab.core.persistence.extensions.PersistenceExtensions');

    var since = ZonedDateTime.now().minusHours(24);

    function upd(srcItemName, lowItemName, highItemName) {
      try {
        var src = items.getItem(srcItemName);
        var min = PersistenceExtensions.minimumSince(src, since);
        var max = PersistenceExtensions.maximumSince(src, since);
        if (min === null || max === null) {
          console.warn('[temp-highlow-24h] No persistence data for ' + srcItemName);
          return;
        }
        items.getItem(lowItemName).postUpdate(String(min.getState()));
        items.getItem(highItemName).postUpdate(String(max.getState()));
        console.info('[temp-highlow-24h] Updated ' + srcItemName + ': low=' + min.getState() + ' high=' + max.getState());
      } catch (e) {
        console.error('[temp-highlow-24h] Error for ' + srcItemName + ': ' + e);
      }
    }

    upd('AmbientWeatherWS2902A_IndoorSensor_Temperature',  'IndoorTemp_24h_Low',  'IndoorTemp_24h_High');
    upd('AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature', 'OutdoorTemp_24h_Low', 'OutdoorTemp_24h_High');
  },
});
