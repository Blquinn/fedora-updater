#!/bin/bash
set -euo pipefail

SPEC="fedora-updater.spec"
NAME=$(rpmspec -q --qf '%{name}' "$SPEC" 2>/dev/null | head -1)
VERSION=$(rpmspec -q --qf '%{version}' "$SPEC" 2>/dev/null | head -1)
TARBALL="${NAME}-${VERSION}.tar.xz"

echo "==> Creating source archive ${TARBALL}"
git archive --prefix="${NAME}-${VERSION}/" -o "$TARBALL" HEAD

echo "==> Building RPM"
rpmbuild -ba "$SPEC" --define "_sourcedir $PWD"

echo "==> Done"
echo "RPMs:  $(ls ~/rpmbuild/RPMS/noarch/${NAME}-${VERSION}-*.rpm 2>/dev/null)"
echo "SRPM:  $(ls ~/rpmbuild/SRPMS/${NAME}-${VERSION}-*.src.rpm 2>/dev/null)"
