# Sensor 223: Bedroom location supersedes Office Hallway

The operator reports moving the same AmbientWeather-WH31E sensor **223** from Office Hallway to the actual **Bedroom** on October 24. The exact physical move time is unknown. A naturally received 66.92°F observation at 23:06:31Z establishes reception, not the move time.

The conservative prospective operational boundary is **2026-10-24T23:14:52Z**. UI Bedroom readings must have an original receipt at or after this boundary and must still satisfy the existing v2 hardware-epoch, model/id and 120-second freshness checks. This boundary records when the new location association becomes usable; it does not claim the sensor moved at that instant.

Home labels the source Bedroom. Shades associates it with Bedroom and retires the former Living Room/Office reference without substituting another room. The prior Office Hallway registry interval remains historical; earlier measurements must not be relabeled as Bedroom history.

`Bedroom_Temperature`, native evidence stream `bedroom`, sensor hardware epoch and JDBC Item **663** retain their stable identities. The helper filename/API retain their legacy names for compatibility. Human OpenHAB Item/rule labels and the same receipt boundary are carried in a separately reviewed v2 patch; live deployment has its own verification record.

This does not activate room-model training, shade control or any new control authority. The four-zone Earthship thermal loop and separate Zigbee `LivingOffice_Shade_Temperature` input are unchanged. The September 30 commissioning/relocation and October 2 deployment receipts remain historical records, superseded for current placement by this note.

Radio reception validation and isolated UI release activation have separate verification records.
