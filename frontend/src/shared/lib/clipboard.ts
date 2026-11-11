/**
 * 클립보드 복사 — HTTP(비보안 문맥)에서는 `navigator.clipboard` 가 없다. 사내 서버가 평문
 * HTTP 인 일이 흔하니 숨긴 textarea + execCommand 로 되돌아간다. 보안 문맥이어도 권한 ·
 * 포커스 때문에 거절될 수 있어, 그때도 같은 길로 한 번 더 해 본다.
 *
 * 둘 다 안 되면 던진다 — 부르는 쪽은 **글을 보여 주고 직접 복사하게** 한다.
 */
export async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return
    } catch {
      // 아래 길로.
    }
  }
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  try {
    if (!document.execCommand('copy')) throw new Error('복사 명령이 거부되었습니다.')
  } finally {
    document.body.removeChild(area)
  }
}
