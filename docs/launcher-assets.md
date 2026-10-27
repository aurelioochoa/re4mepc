# Launcher artwork

Environmental and utility artwork was generated using the built-in image generation tool for this project. The title wordmark and numeral are native text; earlier logo-reference extractions are excluded from current source and releases. No artwork is extracted from an APK. Runtime files live in `re4pc/ui_assets/` and are explicitly included in the release allowlist. Utility icons preserve their generated alpha channels; runtime Pillow processing only crops and resizes images for display.

The case-file redesign follows the user-selected `03-village-case-file.png` concept. The concept remains a build artifact; the runtime uses a cleaned background plate with live Tk text, focusable canvas buttons and a native path entry. Native window decorations remain under the desktop window manager's control. The portable runtime bundles DejaVu Serif alongside its existing sans-serif and monospace fonts.

## case-file.png

Generated with the built-in image generation tool, using the selected concept as the edit target. Opaque 1672 × 941 background plate. Final prompt:

> Use case: precise-object-edit. Edit the supplied launcher reference into a CLEAN BACKGROUND PLATE for a real interactive native desktop launcher. Preserve the exact full-image 16:9 composition and positions: very dark olive/charcoal textured background, aged cream parchment occupying x 1.4%-47.7%, y 8.7%-90.5%; red occult stamp on parchment at upper right with NO letters in stamp, faint map and faded cursive marks as texture; pinned slightly tilted photograph occupying the right half x 48.5%-99%, y 6.7%-68.2%, paperclip at its top. Preserve the EXACT village photograph atmosphere/composition, rural stone church, smoky wooden village, mountain sky. REMOVE ALL UI AND ALL READABLE TEXT everywhere: top navigation/brand/window controls, all Resident Evil 4 Mobile lettering and numeral, tagline, play button INCLUDING its entire red rectangle, readiness icon/text, settings gear and typewriter icons/text/chevrons, separator rules, photo caption, Installation heading, input and buttons, bottom status/links/hints/footer rules. Fill removed areas seamlessly with original surrounding parchment or dark texture as appropriate. Left parchment should be empty for overlaying real title and controls, retaining only worn edges/faint map/red stamp. Bottom right retain subtle map texture but remove readable 'Pueblo' lettering. No new artwork composition, no extra panels, no text, no icons, no controls, no dividers. This is a background plate only, not a UI screenshot. Output same 16:9 aspect ratio as supplied.

## Native title branding — 26 October 2026

The launcher renders its title and numeral with native text. The two earlier
logo-reference extractions, `resident-evil-wordmark.png` and `numeral-4.png`,
are excluded from the source index and release allowlist. The publication
checker rejects either file if it is added again. Previously published Git
history still contains those images; this change does not rewrite that history.
Documentation screenshots remain rendered application captures.

## launcher-preview.png

`docs/launcher-preview.png` is a 1440 × 810 capture of the implemented native launcher in the installed, idle state, captured directly from its host window. The installation readiness indicator sits beside the Installation heading; Achievements occupies the row below Play and has a top navigation entry. It contains generated artwork and host UI only. Layouts were also reviewed at 1280 × 720, 1000 × 600 and 1000 × 800, alongside busy, error and keyboard-focus states. Generated artwork and this preview have reviewed SHA-256 entries in `tools/audit_source.py`.

## forest.png

Use case: stylized-concept. Asset type: background banner for a native Resident Evil 4 Mobile desktop launcher. Create original environmental artwork inspired by Resident Evil 4 survival horror atmosphere: desolate rural European village in fog, leafless forest, distant weathered stone church and crooked timber houses on the RIGHT half, muddy trail, subdued cinematic grain. Wide landscape 1536x1024. Left half very dark charcoal and near-empty fog/tree shadows to support overlaid ivory UI title. Olive gray, charcoal, weathered stone, faint cold fog, very subtle dull red ember detail near village. Moody and atmospheric but village silhouette clearly visible, high quality painted realistic game concept art. No people, no lettering, no logos, no buttons or UI, no watermark. This will be cropped to a wide 3:1 banner, keep important village features around the vertical center.

## icon.png

Use case: logo-brand. Asset type: square 1024x1024 raster desktop application icon for a Resident Evil 4 Mobile launcher. Original RE4-inspired survival horror emblem: one large elegantly distressed ivory numeral "4", sharp angular silhouette, centered on a dark charcoal square with a restrained muted blood-red border inset and faint silhouettes of leafless branches behind it. Flat front-facing icon, iconic and legible at 32px, numeral occupies 75 percent of square, sparse composition, no perspective or surrounding mockup. Text verbatim: "4" only. No extra letters, no watermark, no glossy 3D, no skull, no additional symbols. Keep design inside square; opaque background.

## Additional launcher icons

Three original square icons were generated for the picker: `icon-village.png` (ivory 4 over a foggy village and blood-red moon), `icon-seal.png` (ivory 4 on a red wax seal and black leather), and `icon-bell.png` (ivory 4 with a village church bell). Each prompt requested survival-horror artwork readable at desktop icon sizes, without extra text, mockups or watermarks. The generated PNGs are included unchanged.

## settings.png

Use case: stylized-concept. Asset type: transparent UI icon for Resident Evil 4 inspired desktop game launcher. Single front-facing antique steel cogwheel, worn brushed metal in gray ivory with subtle muted oxblood distress, simple strong silhouette, centered filling 80 percent of square 1024x1024. Survival horror inventory icon style, tactile but clean and legible at 32px. Isolated genuine transparent background. No scenery, no text, no glow, no frame, no shadow outside object, no extra objects.

## backups.png

Use case: stylized-concept. Asset type: transparent UI icon for Resident Evil 4 inspired desktop game launcher save backups. Single vintage typewriter in desaturated gray ivory metal, simple strong silhouette, front three-quarter view, centered filling 80 percent of square 1024x1024. Survival horror inventory icon style, tactile worn metal, restrained detail so readable at 32px. Isolated genuine transparent background. No scenery, no text or visible letters, no glow, no frame, no shadow outside object, no extra objects.


## Settings and achievement artwork — 12 Oct 2026

The built-in image-generation tool generated one blank `paper.png` and one transparent PNG per catalog ID. Original PNGs were copied into `re4pc/ui_assets/` without alpha removal, recoloring or image edits. Runtime processing only crops and resizes for display. The existing `settings.png` cogwheel and `backups.png` typewriter supplied material references. The bell, wrapped pistol and crown were generated first and inspected for consistent lighting, material wear and recognizable silhouettes; their outputs then supplied style references for the remaining eighteen separate generation calls. All icons are original project artwork rather than extracted game assets.

### paper.png

Final prompt; transparent background disabled:

> Use case: stylized-concept. Asset type: reusable opaque blank parchment sheet texture for native case-file forms. Front-facing full-frame rectangular aged cream parchment, warm ivory center #e7d8b9, faint tactile paper fibers, subtle worn edges and subdued brown edge patina. Very quiet nearly uniform pale center for legible black text. No folds through center, no lettering, marks, maps, stamps, objects, scenery, interface or watermark. Square composition. Paper covers entire opaque image.

### Initial style references

`achievement-village.png` final prompt; cogwheel and typewriter references, transparent background enabled:

> Use case: stylized-concept. Asset type: transparent native desktop achievement inventory icon. Generate one original weathered village church bell, aged brass with worn steel bracket, centered three-quarter view, tactile weathered material with restrained oxblood details. Use the supplied cogwheel and typewriter as material and lighting references only, not subjects. Soft upper-left lighting, strong silhouette readable at 72 pixels, square composition, generous 12 percent clear margins. Genuine transparent background, no lettering, scenery, interface, ground shadow or watermark.

For `achievement-first_purchase.png` and `achievement-platinum.png`, the bell and typewriter were the two references, transparent background enabled. Final prompt with the corresponding subject below:

> Use case: stylized-concept. Asset type: transparent native achievement inventory icon. One original SUBJECT, centered consistent three-quarter view and soft upper-left lighting. Match supplied bell, cogwheel and typewriter as MATERIAL references only. Tactile worn steel, aged brass, leather, restrained oxblood details, strong silhouette readable at 72 pixels, generous clear margins, genuine transparent background, no lettering, scenery, interface, ground shadow or watermark.

| Filename | SUBJECT |
| --- | --- |
| `achievement-first_purchase.png` | Merchant’s wrapped pistol, a worn steel handgun partly wrapped in aged brown leather cloth, clearly visible grip and barrel |
| `achievement-platinum.png` | Tarnished platinum crown with one deep oxblood gem, broad regal silhouette |

### Remaining inventory objects

Each asset below uses this final prompt with `SUBJECT` replaced by the corresponding subject. The bell, pistol and crown are the three reference images; transparent background was enabled on each separate call.

> Use case: stylized-concept. Asset type: transparent native achievement inventory icon. One original inventory object: SUBJECT. Centered consistent three-quarter view, soft upper-left lighting. Supplied bell, pistol and crown are approved material/style references only; depict only the requested subject. Tactile worn steel, aged brass, leather, restrained oxblood details, desaturated survival-horror inventory render, strong silhouette readable at 72 pixels. Generous clear margins, no lettering, scenery, interface, ground shadow or watermark. Genuine transparent background.

| Runtime filename | SUBJECT |
| --- | --- |
| `achievement-gigante.png` | Carved stone fist, a clenched hand sculpture of cracked weathered granite |
| `achievement-ashley.png` | Amber brooch in aged brass, simple oval amber cabochon on a worn pin |
| `achievement-verdugo.png` | Armored claw, one articulated worn steel gauntlet with curved finger talons |
| `achievement-salazar.png` | Ornate castellán’s key in aged brass, oversized decorative bow and readable key teeth |
| `achievement-krauser.png` | Worn commando knife, broad steel blade and aged leather handle |
| `achievement-saddler.png` | Ceremonial parasite staff, dark weathered metal shaft with a sculpted branching parasite head |
| `achievement-campaign.png` | Closed leather mission dossier with a plain steel clasp, no writing |
| `achievement-extreme.png` | Riveted steel heart, anatomically simplified heart-shaped metal object with strong silhouette |
| `achievement-first_s.png` | Single silver star medal with a small oxblood fabric ribbon |
| `achievement-all_s.png` | Silver star medal encircled by an aged brass laurel wreath, small oxblood ribbon |
| `achievement-strongest.png` | Winged elite-agent medal in silver steel and aged brass |
| `achievement-mercenary.png` | Worn military dog tags, two blank steel tags on one short chain |
| `achievement-mercenary_master.png` | Dog tags and decorated ammunition belt, one neatly coiled leather belt with brass cartridges and two blank tags |
| `achievement-collector.png` | Compact three-weapon rack, exactly three distinct weapons: pistol, shotgun and rifle arranged on a small wood and metal rack |
| `achievement-arsenal.png` | Five-weapon display case, exactly five distinct miniature weapons arranged inside one open leather-lined steel case |
| `achievement-first_upgrade.png` | Gun oil can and cleaning brush, one small worn steel oil can paired with one short brush |
| `achievement-tuned.png` | Gunsmith’s vise, compact worn steel bench vise with brass adjustment handle |
| `achievement-expert.png` | Precision scope and adjustment tool, one steel telescopic scope paired with one small brass screwdriver |

See [Native case-file windows](dialogs.md) for the host previews, synthetic fixture provenance and reproduction commands. Runtime assets and published previews have explicit reviewed SHA-256 entries in `tools/audit_source.py`; `re4pc/packaging.py` explicitly lists all runtime assets.

### Final arsenal revision

The initial arsenal result included reference objects in the case and was rejected during visual inspection. The shipped `achievement-arsenal.png` was regenerated with the three-weapon rack and wrapped pistol as material references. Its final prompt, with transparent background enabled:

> Use case: stylized-concept. Asset type: transparent native achievement inventory icon. Create one original open five-weapon display case. CONTENTS MUST BE EXACTLY FIVE GUNS ONLY: one small semiautomatic pistol, one revolver, one pump-action shotgun, one scoped bolt-action rifle, one compact submachine gun. Lay these five recognizable miniature firearms in separate leather-lined compartments inside one open worn-steel rectangular case. The supplied inventory images are MATERIAL AND LIGHTING references only, not content to copy. DO NOT INCLUDE a bell, crown, medal, staff, knife, grenade, gem, or any reference object other than firearms. Centered three-quarter view, soft upper-left lighting, tactile worn steel and aged brass fittings, brown leather lining, restrained oxblood wear, strong silhouette readable at 72 pixels. Generous clear margins. Genuine transparent background. No letters, scenery, interface, ground shadow or watermark.

The final set was inspected on parchment in four native review sheets from `tools/preview_dialogs.py --artwork`, displaying every icon at 72 and 192 pixels. All silhouettes are distinct and readable at both sizes. Only the final arsenal revision is packaged; rejected variants remain outside the publication allowlist.

## Final dialog assets (12 October 2026)

Generated with the built-in image-generation tool using the user's three final concepts as visual references. These are individual presentation assets; all labels, controls, selection states and actions are native Tk widgets. Existing cog, typewriter and achievement icons are retained. Generated alpha is preserved; runtime rendering only crops transparent margins and resizes the assets.

| Runtime asset | Reference and purpose |
| --- | --- |
| `re4pc/ui_assets/case-seal.png` | Achievement concept: distressed oxblood circular cult seal on parchment. |
| `re4pc/ui_assets/ribbon-spools.png` | Backup concept: paired worn ribbon spools for snapshot rows and the detail illustration. |
| `re4pc/ui_assets/paperclip.png` | Settings concept: tarnished brass clip at the top of the detail paper. |
| `re4pc/ui_assets/case-paper-v2.png` | Achievement and settings concepts: clean cream parchment with faint map and pen markings along the right margin. |

### Final generation prompts

**case-seal.png** — Use case: stylized-concept. Asset type: one transparent PNG UI decoration for a native Resident Evil 4 Mobile case-file launcher. The supplied image is a STYLE REFERENCE ONLY, not an image to modify. Generate ONLY the round red ink cult seal shown near the top right of the left parchment page, isolated and centered. Match the reference: thin circular distressed oxblood red stamp ring, angular ornate Los Iluminados inspired symmetrical cult insignia in the center with a tall spear, branching wings and pointed ornamental arms. Flat stamped ink, imperfect wear and missing flecks, antique faded red (#9c3a28), crisp readable silhouette when reduced to 80 pixels. No 3D wax, no letters, no words, no extra objects, no parchment, no shadow. Actual transparent background, preserve alpha, generous clear margin, square composition.

**ribbon-spools.png** — Use case: stylized-concept. Asset type: a single transparent inventory icon for the save backup UI of the native Resident Evil 4 Mobile launcher. Supplied image is a STYLE AND OBJECT REFERENCE ONLY. Generate ONLY the small paired typewriter ribbon spools shown at the left of each snapshot row and beside the large typewriter. Worn antique black metal ribbon cartridge with two round brass-bronze spool centers, dark fabric ribbon wrapped around the pair. Three-quarter view from slightly above, long axis diagonally from upper left to lower right. Faithful realistic game inventory render matching the old typewriter in the reference. Warm parchment reflected light, blackened scratched brass, subtle occlusion shadows within the object only. Centered object fully visible, generous transparent margins. No typewriter, no paper, no text, no letters, no pedestal, no background, no cast floor shadow. Actual transparent alpha background. Readable as a 72px UI icon.

**paperclip.png** — Use case: stylized-concept. Asset type: standalone native case-file UI decoration. The attached design is a STYLE AND OBJECT REFERENCE ONLY. Generate ONLY the antique brass paperclip at the upper left of the right parchment page in the reference. A single slender elongated double-loop metal paperclip, warm tarnished bronze brass with dark patina, oriented almost vertical with a slight clockwise lean, gently bent realistic wire, subtle highlights from upper left. Faithful photorealistic small game inventory style. Whole clip visible centered, generous transparent margins, square image composition but clip itself narrow tall. Transparent alpha background. No paper, no parchment, no words, no additional objects, no cast background shadow, no surrounding scene.

**case-paper-v2.png** — Use case: stylized-concept. Asset type: blank parchment background asset for real native case-file UI, NOT a UI mockup. Both supplied images are STYLE REFERENCES ONLY. Generate ONE flat aged cream parchment sheet that matches the paper in these designs: pale warm ivory and sepia paper fibers, naturally weathered distressed brown edge, subtle uneven stains, mostly clean pale center, fine ghosted antique village map sketches fading along the far right margin and faint unreadable pen flourishes in the upper right margin. Broad landscape rectangular composition, fill entire image with paper. The central 75 percent and entire left half must be low contrast and clear enough to overlay dark labels and form fields. Very faint map linework, irregular cracks near outer edge, restrained texture like the references, realistic scanned paper. NO seal, NO red markings, NO paperclip, NO cog, NO typewriter, NO icons, NO titles, NO legible lettering, NO form boxes, NO interface, NO frames, NO perspective, NO drop shadow, NO surrounding background. Flat front-facing paper texture only.
