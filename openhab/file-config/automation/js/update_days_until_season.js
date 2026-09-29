// Staged file-provider equivalent of managed rule update_days_until_season.
// Do not install while the REST-managed rule exists: that would duplicate the writer.
const { rules, triggers, items } = require('openhab');

rules.JSRule({
  id: 'update_days_until_season',
  name: 'Update Days Until Next Season',
  description: 'Updates the season countdown display',
  triggers: [triggers.ItemStateChangeTrigger('Sun_TimeLeft')],
  execute: () => {
    var seconds = parseInt(items.getItem("Sun_TimeLeft").state.toString().split(" ")[0]);
    var next = items.getItem("Sun_NextSeason").state.toString();
    var days = Math.floor(seconds / 86400);
    var emojis = {SPRING: "🌱", SUMMER: "☀️", AUTUMN: "🍂", WINTER: "❄️"};
    var emoji = emojis[next] || "";
    var name = next.charAt(0) + next.slice(1).toLowerCase();
    var result = days + " days until " + name + " " + emoji;
    items.getItem("DaysUntilNextSeason").postUpdate(result);
  },
});
