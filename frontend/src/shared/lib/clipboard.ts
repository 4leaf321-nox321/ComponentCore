/**
 * 클립보드 복사 — HTTP(비보안 문맥)에서는 `navigator.clipboard` 가 없다. 사내 서버가 평문
 * HTTP 인 일이 흔하니 숨긴 textarea + execCommand 로 되돌아간다.
 */
export async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  try {
    if (!document.execCommand('copy')) throw new Error('copy 명령이 거부됐습니다')
  } finally {
    document.body.removeChild(area)
  }
}
