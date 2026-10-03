// STAGED ONLY: retain the managed writer until an attended, qualified cutover.
// Exact managed action; migration does not change freshness or hysteresis logic.
const { rules, triggers, items } = require('openhab');

rules.JSRule({
  id: 'UpdateBatteryIcon',
  name: 'Update Battery Icon',
  triggers: [triggers.GenericCronTrigger('0/30 * * * * ?')],
  execute: () => {
// BEGIN EXACT MANAGED ACTION
// Battery Icon Rule - MDI Icons Version
// Updates BatteryIcon based on SoC and charging state
// Uses Material Design Icons for better visibility on colored backgrounds

// --- Initialization ---
var soc = null;
var current = null;
var logName = "BatteryIconRule";

// --- Helper function to get item state and parse to number ---
function getNumericState(itemName, itemFriendlyName) {
    var itemState = items.getItem(itemName).state;
    var numericValue = null;

    if (itemState !== null && itemState !== undefined && itemState.toString().toUpperCase() !== "NULL" && itemState.toString().toUpperCase() !== "UNDEF") {
        if (typeof itemState === 'number') {
            numericValue = itemState;
        } else {
            var stateString = itemState.toString();
            try {
                numericValue = parseFloat(stateString);
                if (isNaN(numericValue)) {
                    numericValue = null;
                    console.warn(logName + ": " + itemFriendlyName + " state '" + stateString + "' resulted in NaN after parseFloat.");
                }
            } catch (e) {
                numericValue = null;
                console.warn(logName + ": Unexpected error parsing " + itemFriendlyName + " state '" + stateString + "': " + e.message);
            }
        }
    } else {
        console.warn(logName + ": " + itemFriendlyName + " state is NULL or UNDEF: " + itemState);
    }
    return numericValue;
}

// --- Get and Parse SoC value ---
soc = getNumericState("BMS_SOC", "SoC");

// --- Get and Parse Current value ---
current = getNumericState("DCData_Current", "Current");

// --- Define MDI Icon Prefix and Fallback ---
var iconPrefix = "iconify:mdi:";
var fallbackIcon = iconPrefix + "battery-unknown";

// MDI Charging icons (10% increments)
var chargingIcons = {
    c10: iconPrefix + "battery-charging-10",
    c20: iconPrefix + "battery-charging-20",
    c30: iconPrefix + "battery-charging-30",
    c40: iconPrefix + "battery-charging-40",
    c50: iconPrefix + "battery-charging-50",
    c60: iconPrefix + "battery-charging-60",
    c70: iconPrefix + "battery-charging-70",
    c80: iconPrefix + "battery-charging-80",
    c90: iconPrefix + "battery-charging-90",
    c100: iconPrefix + "battery-charging-100"
};

// MDI Discharging/idle icons (10% increments)
var batteryIcons = {
    alert: iconPrefix + "battery-alert",
    outline: iconPrefix + "battery-outline",
    b10: iconPrefix + "battery-10",
    b20: iconPrefix + "battery-20",
    b30: iconPrefix + "battery-30",
    b40: iconPrefix + "battery-40",
    b50: iconPrefix + "battery-50",
    b60: iconPrefix + "battery-60",
    b70: iconPrefix + "battery-70",
    b80: iconPrefix + "battery-80",
    b90: iconPrefix + "battery-90",
    full: iconPrefix + "battery"
};

// --- Handle invalid SoC ---
if (soc === null) {
    var batteryIconItem = items.getItem("BatteryIcon");
    if (batteryIconItem.state !== fallbackIcon) {
        console.warn(logName + ": Invalid SoC value. Setting fallback icon.");
        batteryIconItem.postUpdate(fallbackIcon);
        console.info(logName + ": Updated BatteryIcon to fallback: " + fallbackIcon);
    }
} else {
    // --- Determine Charging Status (hysteresis 2026-07-14: ON > 2.5 A,
    // OFF < 1.0 A — a hard single threshold made the overview flash
    // animation flicker when current hovered at the boundary) ---
    var chargingStatusItem = items.getItem("BatteryChargingStatus");
    var wasCharging = (chargingStatusItem.state === "ON");
    var isCharging = wasCharging ? (current !== null && current >= 1.0)
                                 : (current !== null && current > 2.5);
    var newChargingState = isCharging ? "ON" : "OFF";
    if (chargingStatusItem.state !== newChargingState) {
        chargingStatusItem.postUpdate(newChargingState);
    }
  
    var targetIcon = fallbackIcon;

    if (isCharging) {
        // Charging icons - 10% increments
        if (soc <= 10)      { targetIcon = chargingIcons.c10; }
        else if (soc <= 20) { targetIcon = chargingIcons.c20; }
        else if (soc <= 30) { targetIcon = chargingIcons.c30; }
        else if (soc <= 40) { targetIcon = chargingIcons.c40; }
        else if (soc <= 50) { targetIcon = chargingIcons.c50; }
        else if (soc <= 60) { targetIcon = chargingIcons.c60; }
        else if (soc <= 70) { targetIcon = chargingIcons.c70; }
        else if (soc <= 80) { targetIcon = chargingIcons.c80; }
        else if (soc <= 90) { targetIcon = chargingIcons.c90; }
        else                { targetIcon = chargingIcons.c100; }
    } else {
        // Discharging/idle icons - 10% increments
        if (soc <= 5)       { targetIcon = batteryIcons.alert; }
        else if (soc <= 10) { targetIcon = batteryIcons.outline; }
        else if (soc <= 20) { targetIcon = batteryIcons.b10; }
        else if (soc <= 30) { targetIcon = batteryIcons.b20; }
        else if (soc <= 40) { targetIcon = batteryIcons.b30; }
        else if (soc <= 50) { targetIcon = batteryIcons.b40; }
        else if (soc <= 60) { targetIcon = batteryIcons.b50; }
        else if (soc <= 70) { targetIcon = batteryIcons.b60; }
        else if (soc <= 80) { targetIcon = batteryIcons.b70; }
        else if (soc <= 90) { targetIcon = batteryIcons.b80; }
        else if (soc <= 97) { targetIcon = batteryIcons.b90; }
        else                { targetIcon = batteryIcons.full; }
    }

    // --- Post Update if Changed ---
    var batteryIconItem = items.getItem("BatteryIcon");
    if (batteryIconItem.state !== targetIcon) {
        console.info(logName + ": Updating BatteryIcon to: " + targetIcon + " (SoC=" + soc + "%, Current=" + current + ")");
        batteryIconItem.postUpdate(targetIcon);
    }
}
// END EXACT MANAGED ACTION
  },
});
