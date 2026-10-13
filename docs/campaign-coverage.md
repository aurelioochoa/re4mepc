# Campaign and session coverage

Natural campaign qualification is **pending the user's later playtest**. The
user has no existing natural campaign replay and will test mission completion
later. Existing navigation fixtures set tutorial-clear and
mission-selection records directly, and stage stress requests native stage
changes directly. Those checks cannot stand in for gameplay progression.

A fresh-install, input-only replay on 2026-10-12 reaches the first mission at
tick 604 through title, difficulty, notice and mission selection. It neither
writes userdata nor requests a stage change. Movement, aiming, firing and
interaction inputs reach a manual pickup text panel; the ending gameplay-active
flag is false because that panel is open. No story completion, rank or achievement
is recorded. Local captures and inputs are in `natural-start`; this is partial
entry/interaction evidence, not a campaign pass or a demonstrated engine failure.
A follow-up input-only replay dismisses the reviewed panel using its visible
next arrow and returns to gameplay through tick 1,561. The story/rank records
still contain zero completions and no unlocks. Evidence is in
`natural-start-followup`; the unknown panel is not assigned a guessed menu action.
The later `natural-pilot` replay advances the manual using Enter, walks/collides
through the first village, opens inventory with Escape and opens the handgun
submenu with Enter. Escape initially fails to close that submenu; a verified
inventory cancel route fixes it. Keyboard/controller regression replays return
to gameplay. The same input-only replay is checked inside both package formats.
Door interaction attempts do not change stage and are not recorded as successful
doors. No story rank/completion is recorded.

| Required checkpoint | Current evidence |
|---|---|
| All 22 story missions on Normal, naturally unlocked/completed | Unverified |
| Doors, bosses and companion interactions across the campaign | Unverified |
| Merchant buying/upgrading and inventory use | Synthetic achievement/transaction tests; inventory menu replay; natural merchant progression unverified |
| Death/retry, mission completion and save/load | Native serialization and snapshot tests; natural death/retry/completion unverified |
| Representative missions on Beginner, Professional, Hell and Extreme | Difficulty selector replay; gameplay on those difficulties unverified |
| Mercenary and Coin Shoot modes | Existing record rules/synthetic tests; natural mode play unverified |
| Rank calculation and achievement recovery | Existing synthetic/native record tests; natural end-of-mission rank validation unverified |
| Two-hour continuous session | Incomplete: user stopped the final runtime at its 2,880.043 s checkpoint; earlier 7,200 s evidence belongs to a superseded runtime |
| Twenty mission restart/load cycles | Synthetic native stage lifecycle stress is tracked separately and does not meet natural mission restart coverage |

The session tool performs 20 bounded stage lifecycle cycles, then a two-hour
continuous host session without holding inputs. Each minute it records current
RSS, guest live/heap bytes, open descriptors, queued audio work, gameplay state
and frame percentiles. Warm-up is the first five minutes. It reports actual
resource deltas, not an invented leak threshold, and verifies native save/load.
Inspect occupancy and resources before interpreting a duration check as gameplay
qualification. Failure and interruption remain visible in the external report.

The earlier runtime completed 7,200.035 s with gameplay occupancy 100%, all 20
synthetic stage cycles, released inputs, native save/load, zero descriptor growth
and no pending audio work at samples. Guest live/heap bytes grew by 2,080,112
after warm-up; RSS decreased by 396,857,344 bytes. Other benchmarks and analysis
ran concurrently, so this is a host lifecycle soak with scheduling contention.
It neither proves a natural mission restart nor a stable unmodified campaign.

An isolated 1,200-tick allocation probe attributes all 19,200 retained bytes to
`JNI.GetObjectClass`, which created one persistent 16-byte class handle per tick.
The bridge now reuses the existing FindClass identity cache. The regression
checks matching FindClass/GetObjectClass identities, distinct classes, local-ref
deletion behavior and bounded guest/host allocations over 1,200 calls. The same
real-engine probe after the fix retains zero bytes and keeps 49 host objects.
Raw probes remain external in `session-growth` and `session-growth-fixed`.

The fixed runtime's ten-minute follow-up completes all 20 synthetic cycles and
native save/load with gameplay occupancy 100%, no held inputs, no descriptor or
guest allocation growth after warm-up, and RSS growth of 2,330,624 bytes. This
short follow-up does not satisfy the two-hour gate. At the user's request,
both remaining isolated soak processes were stopped with SIGTERM on
2026-10-13 at 06:27:14 UTC, after copying their checkpoint reports outside the
checkout. Neither process remains running; neither test was restarted.

The final runtime (`menu-back-two-hour`, runtime-source SHA-256
`503295f0794cff95c44ff74e23d9a93f392b8c1801cd79f0740834b037dd82e7`)
last checkpoint records **2,880.043 seconds**, gameplay occupancy 100%, and all
20 synthetic stage cycles. Relative to the five-minute sample, guest live bytes
increase by 448, guest heap bytes by 512, RSS decreases by 9,695,232 bytes and
open descriptors are unchanged. No held inputs or pending audio work appear in
the last sample. The report has `completed: false` and no recorded failure;
termination prevents the end-of-run native save/load check, so that check is not
claimed for this interrupted run. Concurrent execution limits timing conclusions.
**The final two-hour gate remains incomplete.**

The superseded `session-final-two-hour` process also stopped now; its last
checkpoint is 4,320.044 seconds on runtime digest beginning `b15ec886`.
The earlier SIGINT attempt had not terminated it. Its report is incomplete and
does not qualify the final runtime. Checkpoint copies and stop metadata remain
external in `session-stop-20261013`. Natural mission completion is deferred to
the user's later playtest.

```bash
.venv/bin/python tools/validate_session.py --output /external/session
```

A natural campaign report must record each mission and difficulty, input replay
or local checkpoint/capture path, entry/completion ticks, progression evidence,
save/load outcome and encountered failures. Mark every unaudited interaction
explicitly. Isolate reproducible failures before adding regression replays;
use REA/native hooks when host logs cannot explain the state or lifecycle.

For the later manual playtest, record all story missions 1–22 on Normal in
their natural unlock order. For each mission retain a local completion capture,
entry/completion ticks or times, native save/load outcome and any failure.
Record doors, boss fights, companion commands, merchant transactions, inventory
and death/retry when encountered; an unencountered interaction remains unverified.
Then check representative missions on each other difficulty, Mercenary and Coin
Shoot, end-of-mission ranks, achievement recovery and 20 natural restart/load
cycles. Synthetic stage requests remain separate from those checkpoints.
The user will own these manual checks; no completed-campaign claim is made now.
