#!/bin/sh
# Build build/roserpc-x86_64.AppImage: roserpc with its own Python,
# so the host needs no Python. Nothing downloaded is run: the Python AppImage
# is unpacked with unsquashfs, and the output is the AppImage runtime followed
# by a squashfs image, which is all appimagetool produces.
#
# Needs curl, sha256sum, python3 and squashfs-tools. Without squashfs-tools:
#   nix shell nixpkgs#squashfsTools -c tools/build-appimage.sh
set -eu

ARCH=x86_64
PYTHON_VERSION=3.12
PYTHON_IMAGE=python3.12.15-cp312-cp312-manylinux2014_$ARCH.AppImage
PYTHON_URL=https://github.com/niess/python-appimage/releases/download/python$PYTHON_VERSION/$PYTHON_IMAGE
PYTHON_SHA256=a6a9bf619a3e21c5623be144d8ac4e458e1a5b5c133b1cc99b142d6e71b82c76
RUNTIME_RELEASE=20251108
RUNTIME_FILE=runtime-$RUNTIME_RELEASE-$ARCH
RUNTIME_URL=https://github.com/AppImage/type2-runtime/releases/download/$RUNTIME_RELEASE/runtime-$ARCH
RUNTIME_SHA256=2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d

here=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build=$here/build
downloads=$build/downloads
appdir=$build/AppDir
image=$build/roserpc.squashfs
output=$build/roserpc-$ARCH.AppImage

fetch() {
    url=$1 file=$2 sha256=$3
    if [ ! -f "$downloads/$file" ]; then
        curl -fL --retry 3 -o "$downloads/$file.part" "$url"
        mv "$downloads/$file.part" "$downloads/$file"
    fi
    echo "$sha256  $downloads/$file" | sha256sum -c --quiet -
}

# An AppImage's filesystem starts right after its runtime's ELF section headers.
squashfs_offset() {
    python3 - "$1" <<'EOF'
import struct
import sys

ELF_MAGIC = b"\x7fELF"
ELFCLASS64 = 2
E_SHOFF = 0x28
E_SHENTSIZE = 0x3A

with open(sys.argv[1], "rb") as f:
    header = f.read(64)
if header[:4] != ELF_MAGIC or header[4] != ELFCLASS64:
    sys.exit(f"{sys.argv[1]}: not a 64-bit ELF AppImage")
(section_headers,) = struct.unpack_from("<Q", header, E_SHOFF)
entry_size, entries = struct.unpack_from("<HH", header, E_SHENTSIZE)
print(section_headers + entry_size * entries)
EOF
}

mkdir -p "$downloads"
fetch "$PYTHON_URL" "$PYTHON_IMAGE" "$PYTHON_SHA256"
fetch "$RUNTIME_URL" "$RUNTIME_FILE" "$RUNTIME_SHA256"

rm -rf "$appdir"
unsquashfs -q -n -o "$(squashfs_offset "$downloads/$PYTHON_IMAGE")" -d "$appdir" "$downloads/$PYTHON_IMAGE"

python=$appdir/opt/python$PYTHON_VERSION
stdlib=$python/lib/python$PYTHON_VERSION
site=$stdlib/site-packages

# Python's own launcher and metadata, pip and its hook, and what roserpc never
# loads. certifi stays: it is the certificate bundle for HTTPS.
rm -rf "$appdir/AppRun" "$appdir/.DirIcon" "$appdir"/*.desktop "$appdir"/*.png \
    "$appdir/usr/share" "$appdir"/usr/bin/pip* "$python"/bin/pip* \
    "$stdlib/test" "$stdlib/idlelib" "$stdlib/tkinter" "$stdlib/turtledemo" "$stdlib/ensurepip" \
    "$stdlib"/lib-dynload/_tkinter.* "$stdlib"/lib-dynload/_ctypes_test.* \
    "$site/sitecustomize.py" "$site/README.txt" "$site/certifi/tests"
for package in pip build packaging pyproject_hooks; do
    rm -rf "$site/$package" "$site/$package"-*.dist-info
done

mkdir -p "$site/roserpc" "$appdir/usr/share/icons/hicolor/scalable/apps"
cp "$here"/roserpc/*.py "$site/roserpc/"
cp "$here/contrib/appimage/AppRun" "$appdir/AppRun"
chmod +x "$appdir/AppRun"
cp "$here/contrib/appimage/roserpc.desktop" "$here/contrib/appimage/roserpc.svg" "$appdir/"
cp "$here/contrib/appimage/roserpc.svg" "$appdir/usr/share/icons/hicolor/scalable/apps/"
ln -s roserpc.svg "$appdir/.DirIcon"

rm -f "$image"
mksquashfs "$appdir" "$image" -root-owned -noappend -comp zstd -no-progress >/dev/null
cat "$downloads/$RUNTIME_FILE" "$image" >"$output.part"
chmod +x "$output.part"
mv "$output.part" "$output"
rm -f "$image"
echo "$output"
