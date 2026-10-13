# User guide

## Tabs and hotkeys

| Tab | Purpose |
| --- | --- |
| Görünüm | Visualization mode, palette and optional information overlay |
| Kontroller | General aim, key, team, trigger and recoil settings |
| Flick shot | Button binding, knife/previous-weapon keys and sequence state |
| Profiller | Weapon rules and named settings snapshots |
| Durum / Performans | Current state, selected weapon/profile, history and process metrics |

F2 toggles activation, F3 toggles panel visibility and F4 toggles automatic trigger. These global input handlers are not registered in demo mode. Normal startup begins paused.

## Weapon profiles

Open **Profiller → Silaha özel**, choose a weapon or group, edit the form and select **Profili kaydet**. Changes in the form are staged until saved. Automatic selection follows **weapon → group → general** precedence. The main Controls tab still edits general values; it does not rewrite saved weapon rules.

**Genelden kopyala** fills the form from general values without saving it. **Özel ayarı kaldır** removes that rule. **Eldeki silah** selects the currently observed supported weapon. Key bindings, team filters and activation are global.

## Named settings

**Ayar profilleri** saves general values and weapon rules together. Use a name and **Mevcut ayarları kaydet**. Saving the same name replaces that saved profile. Select a profile and **Yükle** to apply it. **Yüklemeyi geri al** restores values from before the last load. Activation is excluded.

The first normal launch creates the protected **Başlangıç ayarlarım** snapshot. It cannot be overwritten or deleted in the UI. Profile files remain local.

## Status and performance

The footer shows why the aim loop is waiting and which weapon profile applies. The dashboard includes application CPU share, working-set RAM, private memory and recent loop durations. P95 is the value at or below which 95% of recent samples fall. Measurements refresh once per second. They do not report game FPS or network latency.

## Flick sequence limits

The first sequence in a player session starts with the weapon held. Subsequent presses from the knife can select the remembered weapon using the configured previous-weapon key, wait for that exact weapon to become ready, perform one sequence and select the knife again. Holding the key does not repeat. Death clears the remembered weapon.

Weapon deployment and fire cooldowns are respected. Ammo decrement confirms a shot, not a hit or kill. R8 and burst-mode weapons are excluded from this sequence. Focus loss and invalid state abort it.

## Local files

`ayar.json`: general settings. `profiller.json`: named and weapon profiles. `gsi_config.json`: local port and secret. `output/`: verified offsets. `map-cache/`: derived local map data. `CS2Tool.log`: local rotating diagnostic log. Do not attach these files publicly without reviewing/redacting their contents.
