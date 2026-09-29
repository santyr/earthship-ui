// Staged file-provider equivalent of managed rule hex_btc_24h_change.
// Do not install while the REST-managed rule exists: that would duplicate the writer.
const { rules, triggers, items } = require('openhab');

rules.JSRule({
  id: 'hex_btc_24h_change',
  name: 'Calculate Bitcoin 24h Price Change',
  triggers: [triggers.ItemStateUpdateTrigger('BTC_USD_Price')],
  execute: () => {
    const output = items.getItem('BTC_Price_24h_PercentChange');
    const price = items.getItem('BTC_USD_Price');
    const current = price.numericState;
    if (typeof current !== 'number' || !Number.isFinite(current)) {
      output.postUpdate('UNDEF');
      return;
    }

    const ZonedDateTime = Java.type('java.time.ZonedDateTime');
    const PersistenceExtensions = Java.type('org.openhab.core.persistence.extensions.PersistenceExtensions');
    const historic = PersistenceExtensions.persistedState(price.rawItem, ZonedDateTime.now().minusHours(24));
    const prior = historic == null ? NaN : Number(String(historic.getState()));
    if (!Number.isFinite(prior)) {
      output.postUpdate('UNDEF');
      return;
    }

    const change = prior !== 0 ? ((current - prior) / prior) * 100 : current > 0 ? 100 : 0;
    output.postUpdate(String(change));
    console.info('[hex_btc_24h_change] BTC 24h change=' + change.toFixed(2) + '%');
  },
});
