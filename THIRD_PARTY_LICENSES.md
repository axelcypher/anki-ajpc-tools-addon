## Third-Party Licenses

This repository is licensed under MIT for AJpC-owned code (see `LICENSE`).

Vendored dependencies included in `vendor/` are licensed separately.
The release package stores platform-specific files under:
- `vendor/win`
- `vendor/linux`
- `vendor/macos_x86_64`
- `vendor/macos_arm64`
- `vendor/common` (shared pure-Python/data packages)

`fugashi` (version `1.5.2`, platform-specific under `vendor/<platform>/fugashi`)
- Declared license: `MIT AND BSD-3-Clause`
- License files:
- `licenses/fugashi.LICENSE.txt` (MIT)
- `licenses/fugashi.LICENSE.mecab.txt` (BSD-3-Clause for MeCab parts)

`unidic-lite` (`vendor/common/unidic_lite`, version `1.0.8`)
- Declared package license: MIT
- Includes UniDic dictionary data under BSD terms
- License files:
- `licenses/unidic-lite.LICENSE.txt` (MIT, wrapper/package)
- `licenses/unidic-lite.LICENSE.unidic.txt` (BSD license for UniDic data)

Notes:

- The authoritative upstream metadata is in:
- `vendor/<platform>/fugashi-1.5.2.dist-info/METADATA`
- `vendor/common/unidic_lite-1.0.8.dist-info/METADATA`
- If vendored dependency versions change, update this file and `licenses/`.
