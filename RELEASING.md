# Releasing madway

The first preview is `v0.1.0-alpha.1`. It is a source release, because the
compositor and desktop helper depend on the target system's wlroots and desktop
libraries. Mark this version as a pre-release when creating a GitHub Release.

Before tagging a version, update the version in CMakeLists.txt and its changelog,
then build and check the source:

```sh
cmake -S . -B build
cmake --build build
./build/madway --version
dbus-run-session -- python3 tests/desktop_smoke.py
git diff --check
```

After committing the reviewed source, create an annotated tag. Export the source
from that tag so local configuration, build files, and ignored personal assets
cannot enter the archive:

```sh
git tag -a v0.1.0-alpha.1 -m "madway 0.1.0-alpha.1: first experimental preview"
mkdir -p build/release
git archive --format=tar.gz --prefix=madway-0.1.0-alpha.1/ \
    --output=build/release/madway-0.1.0-alpha.1.tar.gz v0.1.0-alpha.1
cd build/release
sha256sum madway-0.1.0-alpha.1.tar.gz > SHA256SUMS
cd ../..
```

Extract the archive into a clean directory, build it there, and verify a staged
installation before pushing the branch and tag. Never force-push a release tag.
The archive should contain LICENSE, source, configs, vendored protocol XML, tests,
and documentation; it must contain no personal Longhorn media.

Use the changelog as release notes. A GitHub Release can attach the source archive
and SHA256SUMS. With an authenticated GitHub CLI, after pushing the tag:

```sh
gh release create v0.1.0-alpha.1 \
    build/release/madway-0.1.0-alpha.1.tar.gz build/release/SHA256SUMS \
    --verify-tag --prerelease --title "madway 0.1.0-alpha.1" \
    --notes-file CHANGELOG.md
```
