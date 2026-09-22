# 최신 릴리스 번들을 받는다 — 인터넷 되는 PC(Windows)에서. 서버로 옮기는 것은 scp/WinSCP 로.
#
#   .\fetch-release.ps1                          최신 → .\downloads\
#   .\fetch-release.ps1 -Out D:\bundles          폴더 지정
#   .\fetch-release.ps1 -Version v0.4.3          특정 버전
#   .\fetch-release.ps1 -Apptainer               apptainer .deb 도 함께(폐쇄망 서버용)
#   .\fetch-release.ps1 -Token ghp_xxx           비공개 저장소 — 개인 토큰
#
# **저장소가 비공개다.** 토큰 없이는 GitHub 이 404 를 준다 — 「그런 릴리스가 없다」 로
# 보이지만 사실은 「너는 볼 수 없다」 이다. -Token 을 주거나 GH_TOKEN 환경변수에 둔다.
# 토큰이 있으면 **애셋 API** 로 받는다 — 비공개 저장소에서는 다운로드 주소가 인증을
# 받지 않아 로그인 페이지 HTML 이 tar.gz 라는 이름으로 저장된다.
#
# 받는 것: compcore-<버전>.tar.gz · .sha256 (검증까지 한다)
param(
    [string]$Out = "$PSScriptRoot\downloads",
    [string]$Version = "",
    [string]$Token = "",
    [switch]$Apptainer
)
$ErrorActionPreference = "Stop"
$Repo = "4leaf321-nox321/ComponentCore"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

if (-not $Token) { $Token = $env:GH_TOKEN }
if (-not $Token) { $Token = $env:GITHUB_TOKEN }
$headers = @{ "User-Agent" = "fetch-release" }
if ($Token) { $headers["Authorization"] = "Bearer $Token" }

New-Item -ItemType Directory -Force -Path $Out | Out-Null

$relUrl = if ($Version) { "https://api.github.com/repos/$Repo/releases/tags/$Version" }
          else          { "https://api.github.com/repos/$Repo/releases/latest" }
try {
    $release = Invoke-RestMethod $relUrl -Headers $headers
} catch {
    throw "릴리스를 읽지 못했습니다. 비공개 저장소라면 토큰을 주세요: -Token <개인 토큰>"
}
if (-not $Version) { $Version = $release.tag_name }
Write-Host "==> 버전 $Version → $Out"

$name = "compcore-$Version.tar.gz"
foreach ($f in @($name, "$name.sha256")) {
    Write-Host "    받는 중: $f"
    $dest = Join-Path $Out $f
    if ($Token) {
        $asset = $release.assets | Where-Object { $_.name -eq $f } | Select-Object -First 1
        if (-not $asset) { throw "릴리스 $Version 에 $f 가 없습니다" }
        $h = $headers.Clone(); $h["Accept"] = "application/octet-stream"
        Invoke-WebRequest -Uri $asset.url -OutFile $dest -Headers $h
    } else {
        $url = "https://github.com/$Repo/releases/download/$Version/$f"
        Invoke-WebRequest -Uri $url -OutFile $dest -Headers $headers
    }
}

# 검증 — 절반만 받아진 tar 는 서버에서 푸는 순간에야 드러난다.
$expected = (Get-Content (Join-Path $Out "$name.sha256")).Split(" ")[0].ToLower()
$actual = (Get-FileHash (Join-Path $Out $name) -Algorithm SHA256).Hash.ToLower()
if ($expected -ne $actual) { throw "체크섬이 다릅니다 — 다시 받으세요. ($name)" }
Write-Host "    체크섬 OK"

if ($Apptainer) {
    $ap = Invoke-RestMethod "https://api.github.com/repos/apptainer/apptainer/releases/latest" -Headers @{ "User-Agent" = "fetch-release" }
    $deb = $ap.assets | Where-Object { $_.name -match '^apptainer_[0-9.]+_amd64\.deb$' } | Select-Object -First 1
    if ($deb) {
        Write-Host "    받는 중: $($deb.name)"
        Invoke-WebRequest -Uri $deb.browser_download_url -OutFile (Join-Path $Out $deb.name) -Headers @{ "User-Agent" = "fetch-release" }
    } else { Write-Warning "apptainer .deb 를 찾지 못했습니다 — https://github.com/apptainer/apptainer/releases 에서 직접" }
}

Write-Host ""
Write-Host "[OK] $Out 에 받았습니다. 서버로 옮기기 (계정·IP 는 자기 것으로):"
Write-Host "     scp `"$Out\$name`" `"$Out\$name.sha256`" <계정>@<서버IP>:~/"
