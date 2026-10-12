# Local launcher achievements

Open **Achievements** in the launcher to see 21 local achievements with icons,
unlock dates, progress and saved captures. The list combines classic Resident Evil 4 encounter titles with
completion milestones actually present in the Mobile Edition engine. These are
launcher achievements; they do not sync to Google Play Games, Game Center or Steam.

| Achievement | Mobile Edition requirement |
| --- | --- |
| It Begins With a Ring | Clear story mission 1, Bloodthirsty |
| A Rock and a Hard Place | Clear mission 4, The Giant's Den (El Gigante) |
| Secure Ashley | Clear mission 5, Rescue Ashley |
| A Terrifying Assassin | Clear mission 12, The Strongest Assassin (Verdugo) |
| The Castellan Falls | Clear mission 14, Strange Castellan (Salazar) |
| The Ties That Bind | Clear mission 20, The Price of Power (Krauser) |
| We're Going Home | Clear mission 22, Throwdown (Saddler) |
| Mission Complete | Clear all 22 story missions on one difficulty |
| A Heart of Steel | Clear all 22 story missions on Extreme |
| A Cut Above | Earn an S rank in any story mission |
| S Rank Agent | Earn S ranks in all 22 story missions on one difficulty |
| The Strongest Agent | Earn all 110 story S ranks across five difficulties |
| Hired Gun | Clear a Mercenary mission |
| Mercenary Master | Clear all 44 Mercenary missions |
| What Are Ya Buying? | Buy a weapon from the Merchant |
| Arms Collector | Buy three different weapons |
| Gun Fanatic | Buy five different weapons |
| My Preferred Piece | Purchase one weapon tune-up |
| Custom Made | Purchase five weapon tune-ups |
| High-Caliber | Purchase ten weapon tune-ups |
| Legend of the Village (Platinum) | Unlock all 20 other achievements |

The mobile difficulties are Beginner, Normal, Professional, Hell and Extreme.
Extreme is the highest, so the classic A Heart of Steel achievement uses that
mode. Training mission zero never counts. Console requirements without a verified
mobile equivalent, such as bottle caps, Del Lago and alternate costumes, are
excluded. Boss achievements use the corresponding mission completion record.

Weapon purchase and upgrade counters begin with transactions observed by this
launcher. Starter equipment, item pickups, ammunition purchases, shop browsing
and default weapon-level initialization do not count. The engine does not keep
a verifiable historical purchase ledger, so these goals cannot be recovered from
old inventory alone. Purchase and tune-up receipts are committed after a successful
save of the mission/inventory section; loading a save discards pending receipts.
The six new weapon goals are custom launcher challenges, and the Platinum is a
new meta achievement. Existing achievement dates and records remain compatible.

## Icons and unlock captures

Each row has a drawn badge, with brighter earned icons and a platinum crown for
Legend of the Village. The badges are original vector artwork rendered by the
launcher, without redistributing game artwork. Saved screenshots appear as
thumbnails with **View screenshot**; **Play clip** opens a saved MP4 in the desktop
video player.

In **Settings & controls → Achievements**, choose **off**, **screenshot**, **clip**
or **both**. Screenshot is the default. Replay length can be set from 5 to 15
seconds. Clips are silent 400 × 240 MP4s recorded at 5 FPS; they include up to the
chosen duration ending at the successful save that unlocks the achievement.
Clips enabled during a shorter session contain only the available frames.
Screenshot mode reads the framebuffer only when an unlock occurs. Clip modes
keep a bounded rolling buffer and add periodic framebuffer readbacks. Encoding
runs in a background worker; optional capture errors never revoke achievements.

Captures are stored under `achievement-media/` in the imported installation,
and filenames are linked from the achievement record. Several achievements earned
in one save share the same capture. Captures are taken after the native frame
finishes drawing, before host diagnostic overlays. Recovering achievements from
old saves does not generate images of events that were never recorded.

The save backup contains achievement records and capture references, but excludes
the larger media directory to keep automatic snapshots fast. Copy
`achievement-media/` alongside an installation when moving it. A restored backup
can open its linked media when those files are still present; missing captures
are reported by the launcher. References added after background encoding become
part of the next save snapshot or manual backup.

## Recording and recovery

The runtime reads the original engine's mission flags and per-difficulty ranks
after successful native loads and saves of the relevant sections. It does not
change native mission records, invent high scores or unlock paid content. Failed
or interrupted saves do not award achievements from unsaved progress.

Existing saves are recognized the next time the game loads them. Their recorded
dates reflect when the launcher detected the achievement; original unlock dates
are unavailable. Unlocks remain earned if the game resets its native progress.
Restoring an older full backup also restores its achievement history, then a
later game load can recover any milestones still supported by native records.

Records live in `saves/launcher-achievements.json` in the selected installation.
Writes use an atomic replacement, and completed-save snapshots include the file.
Each installation has its own records. The launcher reads these small snapshots
without launching the engine. Close the game and choose **Refresh** to update an
already open achievements window.

A malformed achievement file is preserved and reported rather than silently
overwritten. Optional achievement-record failures are logged without preventing
the engine from finishing its own save or load.

## Original engine findings

Inspection of the supported Android libraries found native mission-clear flags,
story ranks, Mercenary scores and Coin Shoot records, but no achievement, trophy,
medal, Game Center or leaderboard integration names. All 387 entries of the
original `common.h2z` archive were decoded locally; its text definitions have no
achievement catalog. This does not establish what every historical mobile build
contained, and the APK's Java wrapper was unavailable for inspection.

`Bio4_CTTask_Ending::Set_EndingCheck` explicitly checks all 22 story missions on
one difficulty, all S ranks on one difficulty, and all S ranks across the five
difficulties. The original localized ending messages confirm these milestones.
The host uses audited `Bio4_UserData::GetRank` and `GetMissionClearFlag` layouts;
the runtime's existing library-hash validation gates these hooks. Coin Shoot's
ranking table includes initial score thresholds, so those scores are not treated
as evidence of player-earned achievements. Extra-product flags include purchased
content and are also excluded.

## Historical online research

Wayback Machine retrieval found original storefront pages rather than the newer
2023 iOS remake:

- [Apple's June 2012 listing](https://web.archive.org/web/20120613194026/http://itunes.apple.com/us/app/resident-evil-4/id322523436)
  describes Platinum version 1.04.10, Mercenary Mode, Coin Shoot and difficulty
  choices, without advertising Game Center or achievements.
- [Apple's September 2015 listing](https://web.archive.org/web/20150906160111/https://itunes.apple.com/us/app/resident-evil-4-platinum/id322523436?mt=8&at=10l8HM%2526uo=4)
  still lists version 1.04.10. A preserved player review asks for Game Center,
  supporting the inference that this version lacked it.
- [Google Play's February 2017 listing](https://web.archive.org/web/20170222040333/https://play.google.com/store/apps/details?id=jjp.co.capcom.android.googleplay.bio4)
  describes Android version 1.01.01 and its modes without advertising Play Games
  achievements. Earlier 2014/2015 pages mention achievements only in other
  recommended apps, which are not evidence about RE4.

Internet Archive metadata was also searched for the original iOS bundle
`jp.co.capcom.res4`; it did not provide an achievement list. The research supports
adding local achievements, but absence from archived descriptions is not proof
that no release ever had an achievement service.
