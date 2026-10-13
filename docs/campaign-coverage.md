# Campaign and session coverage

Natural campaign qualification is **incomplete**. The user has no existing
natural campaign replay. Existing navigation fixtures set tutorial-clear and
mission-selection records directly, and stage stress requests native stage
changes directly. Those checks cannot stand in for gameplay progression.

A fresh-install, input-only replay on 2026-10-12 reaches the first mission at
tick 604 through title, difficulty, notice and mission selection. It neither
writes userdata nor requests a stage change. Movement, aiming, firing and
interaction inputs reach a manual pickup text panel; the ending gameplay-active
flag is false because that panel is open. No story completion, rank or achievement
is recorded. Local captures and inputs are in `natural-start`; this is partial
entry/interaction evidence, not a campaign pass or a demonstrated engine failure.

| Required checkpoint | Current evidence |
|---|---|
| All 22 story missions on Normal, naturally unlocked/completed | Unverified |
| Doors, bosses and companion interactions across the campaign | Unverified |
| Merchant buying/upgrading and inventory use | Synthetic achievement/transaction tests; inventory menu replay; natural merchant progression unverified |
| Death/retry, mission completion and save/load | Native serialization and snapshot tests; natural death/retry/completion unverified |
| Representative missions on Beginner, Professional, Hell and Extreme | Difficulty selector replay; gameplay on those difficulties unverified |
| Mercenary and Coin Shoot modes | Existing record rules/synthetic tests; natural mode play unverified |
| Rank calculation and achievement recovery | Existing synthetic/native record tests; natural end-of-mission rank validation unverified |
| Two-hour continuous session | Isolated soak records duration, gameplay occupancy and resource samples; qualification awaits the completed report |
| Twenty mission restart/load cycles | Synthetic native stage lifecycle stress is tracked separately and does not meet natural mission restart coverage |

The session tool performs 20 bounded stage lifecycle cycles, then a two-hour
continuous host session without holding inputs. Each minute it records current
RSS, guest live/heap bytes, open descriptors, queued audio work, gameplay state
and frame percentiles. Warm-up is the first five minutes. It reports actual
resource deltas, not an invented leak threshold, and verifies native save/load.
Inspect occupancy and resources before interpreting a duration check as gameplay
qualification. Failure and interruption remain visible in the external report.

```bash
.venv/bin/python tools/validate_session.py --output /external/session
```

A natural campaign report must record each mission and difficulty, input replay
or local checkpoint/capture path, entry/completion ticks, progression evidence,
save/load outcome and encountered failures. Mark every unaudited interaction
explicitly. Isolate reproducible failures before adding regression replays;
use REA/native hooks when host logs cannot explain the state or lifecycle.
