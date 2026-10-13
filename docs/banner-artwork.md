# README banner artwork

The active banner is `docs/readme-banner.png` (2172 × 724, 3:1), created with the built-in image generation tool on 2026-10-11. It is original generated fan artwork featuring two Tux penguins dressed as classic Leon S. Kennedy and Ashley Graham. The subtitle reads **Linux PC port**.

## Visual references

- [Original Mobile Edition gameplay gallery — MobyGames](https://www.mobygames.com/game/42794/resident-evil-4-mobile-edition/screenshots/): village textures, over-the-shoulder aiming and red laser sight. [Reference image](https://cdn.mobygames.com/d6238dc0-ac1c-11ed-9c12-02420a00012f.webp).
- [Resident Evil 4 (2005) artwork gallery — LaunchBox](https://gamesdb.launchbox-app.com/games/details/7502-resident-evil-4-2005): forest atmosphere, lighting, tactical outfit and handgun pose. [Reference image](https://images.launchbox-app.com/14c6ccef-6621-4925-818a-0ec3fe2e89ff.jpg).

The internet images guided the illustration; the generated banner is not an in-game screenshot. Resident Evil characters and source game artwork belong to Capcom. Tux is the Linux mascot. The README gameplay mosaic separately shows four actual Linux port captures from desktop gameplay tests.

## Generation prompts

The initial generation used the two reference images above. Both following edits used the preceding generated banner as their image input.

### Initial generation

```text
Use case: stylized-concept.
Asset type: final illustrated README header for the re4mepc open-source Resident Evil 4 Mobile Linux compatibility host.
Create one finished wide landscape banner, aspect ratio exactly 3:1, ideally 1800 × 600 px.
Reference image 1: original Resident Evil 4 Mobile gameplay. Use only as a reference for muddy rural Spanish village scenery, old wooden fences, over-the-shoulder survival horror mood, muted olive-brown palette, and a thin red handgun laser.
Reference image 2: classic Resident Evil 4 artwork. Use only as a reference for dramatic blue-grey fog, bare trees, tactical clothing, heroic handgun pose and poster lighting.
These are visual references, not edit targets. Produce a new original fan illustration rather than a screenshot or pasted collage.
Main subject: Tux, the unmistakable Linux penguin mascot, dressed as classic Leon S. Kennedy. Retain Tux's rounded black-and-white penguin body, white belly and face, orange-yellow beak, orange webbed feet and flipper anatomy. Give him Leon's short brown leather jacket with thick pale shearling collar, black tactical underlayer, brown shoulder holster straps, utility belt and leg holster. No human face, no human skin, no human hands. Tux holds a compact handgun carefully in his gloved flippers in a purposeful classic Leon ready pose, angled toward the far right, with a subtle red laser extending into fog. Express confident determination while still looking recognizably like Tux.
Composition: follow the existing README banner's text-on-left, artwork-on-right hierarchy. Reserve the left 42 percent as elegant dark charcoal negative space for strong readable typography; place Tux prominently in the right half, his full recognizable silhouette and feet inside the canvas. Behind him, a crumbling rural village, crooked rooftops, small distant bell tower, leafless trees and mist. Perspective and grounded shadows; painterly detailed game key-art illustration, not glossy plastic or a childish cartoon. The atmosphere combines sepia village earth with cold forest haze and restrained warm edge lighting on the jacket. Good contrast, textured illustration, disciplined composition.
Text: render ONLY these three exact lines, readable and properly spelled:
small uppercase kicker "RESIDENT EVIL 4 MOBILE"
large primary title "re4mepc" (r e 4 m e p c, all lowercase except digit)
smaller subtitle "Linux PC host"
Use crisp ivory display typography, a slightly weathered confident title and a muted warm-gold kicker. Keep generous margins and strong readability at GitHub README width. No extra tagline, no logos other than Tux, no CAPCOM mark, no phone frame, no desktop UI, no HUD, no badges, no watermark, no gore. Final output must be the completed raster banner, no mockup.
```

### Character and laser corrections

```text
Use case: precise-object-edit.
Edit target: image 1, the generated re4mepc README banner. Produce a final replacement banner preserving exactly its 3:1 wide aspect ratio and 2172 × 724 canvas if possible.
Keep the left text area, the exact three text lines "RESIDENT EVIL 4 MOBILE", "re4mepc", "Linux PC host", their typography, readability, margins and dark backdrop unchanged. Keep the existing cinematic rural village, bell tower, mist, lighting and overall painterly game-art style.
Make these three requested corrections:
1. Correct the pistol laser. It must be a single perfectly STRAIGHT, thin red beam, geometrically collinear with the barrel's direction, starting exactly at the laser emitter just below the muzzle and extending unbroken to the right edge. No bend, no curve, no multiple beams, no floating separate segment. Maintain a realistic subtle glow. Align the gun and emitter as needed so the beam is visibly straight.
2. Add classic 2005 Leon S. Kennedy hair to the main Tux: ash-blond/light-brown, straight layered hair with a long side-swept fringe and characteristic side part. Keep his unmistakable penguin eyes, yellow beak, black-and-white penguin face, rounded white belly, orange feet, brown shearling jacket and tactical outfit. Hair should be believable as a stylized wig on a Tux penguin, no human head or skin.
3. Add a SECOND Tux penguin dressed unmistakably as classic Ashley Graham, standing alongside Leon-Tux in the right-hand artwork area, slightly behind him and smaller. She has shoulder-length golden-blond bob hair with side-swept bangs, an orange sleeveless knit turtleneck sweater, a small green scarf, green tartan mini skirt and dark leggings. Preserve visible penguin traits: black-and-white face, yellow beak, white penguin belly where exposed, rounded penguin proportions, flippers and orange webbed feet. Give Ashley-Tux a concerned but brave expression and natural companion pose. Keep both characters' feet within the canvas. Place her behind and to the right of Leon-Tux but out of the laser's path; the beam should run above her head, with no collision or occlusion. Adjust main Tux a little left within the right half if needed to fit the companion, while keeping the text completely unchanged and unobscured.
Both subjects are Tux mascots wearing character costumes, not human characters. Match their scale, perspective, detailed material rendering, ground contact, highlights and shadows. Exactly two Tux penguins. No additional text or marks, no HUD, no human hands, no gore.
```

### Final subtitle correction

```text
Use case: text-localization. Edit the supplied finished README banner. Change ONLY the subtitle text from "Linux PC host" to the exact text "Linux PC port". Match the same font, size, ivory color, baseline and placement. Keep the other exact text "RESIDENT EVIL 4 MOBILE" and "re4mepc" unchanged. Preserve every other visual element: the two Tux penguins dressed as classic Leon and Ashley, their hair and costumes, the perfectly straight red laser, village, bell tower, fog, composition, colors, lighting and 3:1 aspect ratio. The final subtitle must read "Linux PC port" with no extra characters. Return one completed banner.
```

## Publication

Only the final generated banner is stored in the repository. The source audit approves its exact path and SHA-256, rather than allowing arbitrary PNGs or game assets. When replacing the banner, visually review the new result and update `DOCUMENTATION_IMAGES` in `tools/audit_source.py`.

The earlier vector banner remains at `docs/readme-banner.svg`.
