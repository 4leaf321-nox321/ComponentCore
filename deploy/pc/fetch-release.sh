#!/usr/bin/env bash
# 최신 릴리스 번들을 받는다 — 인터넷 되는 PC(맥 · 리눅스)에서.
#
#   ./fetch-release.sh                       최신 → ./downloads/
#   ./fetch-release.sh -o ~/bundles          폴더 지정
#   ./fetch-release.sh -v v0.4.3             특정 버전
#   ./fetch-release.sh -a                    apptainer .deb 도 함께(폐쇄망 서버용)
#
# **저장소가 비공개다.** 토큰 없이는 GitHub 이 404 를 준다 — 「그런 릴리스가 없다」 로
# 보이지만 사실은 「너는 볼 수 없다」 이다. 개인 토큰(repo 읽기)을 환경변수로 준다:
#
#   GH_TOKEN=ghp_xxx ./fetch-release.sh
#
# 토큰이 있으면 **애셋 API** 로 받는다(`/releases/assets/<id>` + octet-stream).
# 비공개 저장소에서는 browser_download_url 이 인증을 받지 않는다 — 로그인 페이지의
# HTML 이 tar.gz 라는 이름으로 저장되고, 그 사실은 서버에서 푸는 순간에 드러난다.
set -euo pipefail
REPO="4leaf321-nox321/ComponentCore"
OUT="$(dirname "$0")/downloads"; VERSION=""; APPTAINER=0
TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"
while getopts ":o:v:ah" opt; do
    case "$opt" in
        o) OUT="$OPTARG" ;; v) VERSION="$OPTARG" ;; a) APPTAINER=1 ;;
        h) sed -n '2,16p' "$0"; exit 0 ;; *) echo "모르는 옵션 — -h"; exit 1 ;;
    esac
done
mkdir -p "$OUT"

api() {  # $1 = 주소. 토큰이 있으면 붙인다.
    if [[ -n "$TOKEN" ]]; then curl -fsSL -H "Authorization: Bearer $TOKEN" \
        -H "X-GitHub-Api-Version: 2022-11-28" "$1"
    else curl -fsSL "$1"; fi
}

REL_URL="https://api.github.com/repos/$REPO/releases/latest"
[[ -n "$VERSION" ]] && REL_URL="https://api.github.com/repos/$REPO/releases/tags/$VERSION"
# curl 의 「(22) error: 404」 는 여기서 숨긴다 — 아래 안내가 그 404 의 뜻이다.
if ! RELEASE="$(api "$REL_URL" 2>/dev/null)"; then
    echo "릴리스를 읽지 못했습니다. 비공개 저장소라면 GH_TOKEN 을 주세요:"
    echo "    GH_TOKEN=<개인 토큰> $0 ${VERSION:+-v $VERSION}"
    exit 1
fi
[[ -n "$VERSION" ]] || VERSION="$(printf '%s' "$RELEASE" | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -n1)"
[[ -n "$VERSION" ]] || { echo "최신 버전을 알아내지 못했습니다 — -v 로 주세요"; exit 1; }
echo "==> 버전 $VERSION → $OUT"

NAME="compcore-$VERSION.tar.gz"
# 애셋 하나의 JSON 덩어리 안에 url 과 name 이 함께 있다 — '{' 로 쪼개 이름으로 고른다.
asset_url() {
    printf '%s' "$RELEASE" | tr '{' '\n' \
        | grep -F "\"name\": \"$1\"" \
        | grep -o "https://api.github.com/repos/[^\"]*/releases/assets/[0-9]*" | head -n1
}
for f in "$NAME" "$NAME.sha256"; do
    echo "    받는 중: $f"
    if [[ -n "$TOKEN" ]]; then
        url="$(asset_url "$f")"
        [[ -n "$url" ]] || { echo "릴리스 $VERSION 에 $f 가 없습니다"; exit 1; }
        curl -fL --progress-bar -H "Authorization: Bearer $TOKEN" \
            -H "Accept: application/octet-stream" -o "$OUT/$f" "$url"
    else
        curl -fL --progress-bar -o "$OUT/$f" \
            "https://github.com/$REPO/releases/download/$VERSION/$f"
    fi
done
( cd "$OUT" && sha256sum -c "$NAME.sha256" ) || { echo "체크섬이 다릅니다 — 다시 받으세요."; exit 1; }
if [[ $APPTAINER -eq 1 ]]; then
    URL="$(curl -fsSL https://api.github.com/repos/apptainer/apptainer/releases/latest | grep -oE 'https://[^"]*/apptainer_[0-9.]+_amd64\.deb' | head -n1)"
    if [[ -n "$URL" ]]; then echo "    받는 중: $(basename "$URL")"; curl -fL --progress-bar -o "$OUT/$(basename "$URL")" "$URL"
    else echo "경고: apptainer .deb 를 찾지 못했습니다 — https://github.com/apptainer/apptainer/releases 에서 직접"; fi
fi
echo
echo "[OK] $OUT 에 받았습니다. 서버로 옮기기 (계정·IP 는 자기 것으로):"
echo "     scp $OUT/$NAME $OUT/$NAME.sha256 <계정>@<서버IP>:~/"
