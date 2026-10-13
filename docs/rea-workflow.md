# Native analysis workflow

REA is a development tool only. Neither game launch nor either distribution
format requires Node, Java, Ghidra or REA. Analysis output and supported game
libraries belong outside the source checkout.

The initial toolchain uses REA 6.4.0, Ghidra 12.1.4 and a full x86_64 JDK 21.
These match the [REA provider baseline](https://github.com/morluto/rea/blob/main/docs/installation.md#ghidra).
The local run used Temurin 21.0.12.1+1 and Node 22.23.1. Package downloads were
hashed before extraction; REA was installed under `/tmp/re4-roadmap/toolchain`
without running `rea setup` or changing agent configuration.

| Download | SHA-256 |
|---|---|
| rea-agents-6.4.0.tgz | 59eb1604b8db75f522d4a975c36ce6b4a2ad465e43bad165f9a8f728391db9b8 |
| ghidra_12.1.4_PUBLIC_20260921.zip | ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db |
| OpenJDK21U-jdk_x64_linux_hotspot_21.0.12.1_1.tar.gz | ce79869e1307ed8ee1e2baa86a412b1eb5b75d10a01006d788a6f968bcfaee94 |

The Ghidra digest was compared with its GitHub release asset digest. The JDK
digest was compared with Adoptium release metadata. REA's npm lock records the
registry integrity value; the table additionally identifies the downloaded
package bytes. Paths and release metadata are local evidence, not shipped game
resources.

With the extracted installations available, run:

```bash
.venv/bin/python tools/rea_workflow.py \
  --rea /external/toolchain/rea/node_modules/.bin/rea \
  --ghidra /external/toolchain/ghidra_12.1.4_PUBLIC \
  --java-home /external/toolchain/jdk-21 \
  --output /external/analysis/rea \
  --package-artifact /external/toolchain/rea-agents-6.4.0.tgz
```

The verifier checks provider readiness, exact tool versions and supported engine
hashes. It compares three named functions per library with ELF/Capstone entries,
instruction boundaries and mnemonics, including ARM and Thumb examples. It saves
raw instructions, dossiers, pseudocode, provider errors and snapshots externally.
A provider error or mapping disagreement leaves `gate_passed` false and returns
an unsuccessful process status. The source tests exercise known good evidence
and independently corrupt identity, addresses, boundaries and decoding.

ELF function values retain the Thumb selector in bit zero. Capstone and Ghidra
instruction addresses in Capstone use `ELF_value & ~1`. Ghidra rebases these shared libraries by `0x10000` with its default ELF loader. The verifier reads `inspect-native-load-image` and checks the source file offset and backing digest at each rebased entry before comparing instructions. Runtime addresses add the host shared
memory base and a module offset: zero for the eruption library and `0x200000`
for `libbio4af.so`. Runtime `ArmRuntime.call` uses the original symbol value,
including its ISA selector. File offsets use the containing ELF section's offset
plus the instruction address minus the section virtual address.

For focused investigations, use the [REA CLI](https://github.com/morluto/rea/blob/main/docs/cli.md):

```bash
rea function /external/game/lib/libbio4af.so SYMBOL --provider ghidra --json
rea decompile /external/game/lib/libbio4af.so ADDRESS --provider ghidra --json
rea xrefs /external/game/lib/libbio4af.so ADDRESS --provider ghidra --json
```

Snapshots cache exact queries and are not a persistent provider database. A new
query may re-import/analyze the library. Static references and pseudocode explain
runtime observations; they do not measure execution time. Preserve provider
limitations when interpreting incomplete call graphs or decompilation.
