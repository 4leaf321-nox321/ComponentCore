/**
 * 수 · `=식` 을 적는 글자 칸 — **치는 동안의 글자를 그대로 둔다.**
 *
 * 칠 때마다 수로 바꿔 다시 그리면 「1.」 이 1 이 되어 0.5 · 1.5 같은 소수를 한 글자씩 칠 수
 * 없었다(2026-10-04 점검). 그래서 보이는 글자는 칸이 들고, 바깥에는 칠 때마다 알린다(`onText` —
 * 수로 바꾸는 것은 부르는 쪽의 일이다). 바깥 값이 **다른 데서** 바뀌면(초기화 · 다른 창) 따라간다 —
 * 지금 글자가 뜻하는 수와 바깥 값이 다를 때만.
 */

import { useEffect, useState } from 'react'
import type { ComponentProps } from 'react'

import { Input } from '@/shared/components/ui/input'

/** 견줄 모양 — 수로 읽히는 글자는 그 수의 글자로(「1.」 · 「1.0」 → 「1」), 나머지는 그대로. */
function canonical(text: string): string {
  const trimmed = text.trim()
  if (trimmed !== '' && !trimmed.startsWith('=') && Number.isFinite(Number(trimmed))) return String(Number(trimmed))
  return text
}

export function NumberText({
  value,
  onText,
  ...rest
}: Omit<ComponentProps<typeof Input>, 'value' | 'onChange'> & {
  value: unknown
  onText: (text: string) => void
}) {
  const shown = value === null || value === undefined ? '' : String(value)
  const [text, setText] = useState(shown)
  useEffect(() => {
    if (canonical(text) !== canonical(shown)) setText(shown)
    // 바깥 값이 바뀔 때만 견준다 — 치는 동안(글자만 바뀔 때)은 그대로 둔다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shown])
  return (
    <Input
      {...rest}
      value={text}
      onChange={(event) => {
        setText(event.target.value)
        onText(event.target.value)
      }}
    />
  )
}
