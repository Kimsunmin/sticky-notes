#!/bin/sh
# 메타정보 파일의 가장 위 release 가 앱 버전이다. .deb, snap, 릴리스 태그가 모두 이 값을 쓴다.
sed -n 's/.*<release version="\([^"]*\)".*/\1/p' "$(dirname "$0")/../data/io.github.kimsunmin.StickyNotes.metainfo.xml" | head -n 1
