# Portable achievement captures and backups

Achievements offers **Export selected** and **Export all** while the installation
is stopped. The gallery ZIP contains original PNG/MP4 files once each, plus
`achievements.json` with achievement IDs, titles, unlock timestamps, media links,
payload sizes/hashes and missing references. Export all includes all catalog
entries, independently of the current search/filter. Missing gallery captures
are listed; other readable originals still export.

```bash
./re4pc.sh export-achievements /destination/captures.zip --game /path/to/game
./re4pc.sh export-achievements /destination/captures.zip \
  --achievement village --achievement gigante --game /path/to/game
./re4pc.sh export-backup SNAPSHOT_ID /destination/portable.zip \
  --include-media --game /path/to/game
./re4pc.sh import-backup /destination/portable.zip --game /other/installation
./re4pc.sh restore-backup IMPORTED_SNAPSHOT_ID --game /other/installation
```

The backup window's **Include achievement media** checkbox starts unchecked.
Save-only export keeps the existing version-one archive. Checking the option
creates a separate version-one `re4mepc-save-media` bundle. References come from
the selected snapshot's saved achievement record, not current progress. Every
referenced file must exist; missing media causes bundle export to fail clearly.

A bundle contains `bundle.json`, the unchanged save-only `save.zip`, and
`media/NAME` payloads. Its manifest lists exact sizes/SHA-256 hashes and snapshot
identity. The manifest checksum is SHA-256 of canonical JSON with the checksum
field omitted. Checksums detect corruption; they are not an authentication
signature. No imported game libraries, settings, caches or unrelated media are
included.

Import recognizes both formats under the existing installation lock. It streams
payloads to staging files, validates the whole archive and nested save set,
checks exact media references and all destination conflicts, then publishes
media before publishing an imported snapshot. Identical destination media is
reused; different contents or symbolic links are rejected. Import does not
activate saves: use **Restore** afterwards. An interrupted import may leave
validated, reusable media, while active saves remain unchanged. Interrupted
exports do not publish a partial destination. Existing destination exports are
never overwritten.

Existing save limits remain 256 MiB / 4,096 files. Additional media is limited
to 1 GiB / 4,096 files, with a 2 MiB bundle manifest. Unsafe paths, duplicate or
unlisted members, nonregular payloads, unsupported versions, corrupt checksums,
oversized payloads and inconsistent references are rejected. ZIP payloads are
streamed in bounded chunks; the existing bounded save publication path can still
hold a complete save set in memory.
