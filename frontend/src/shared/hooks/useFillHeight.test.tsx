import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useFillHeight } from '@/shared/hooks/useFillHeight'

/** 해석 조건과 같은 모양 — 불러오는 동안은 뼈대만, 다 불러오면 그제야 잴 자리가 선다. */
function Late({ ready }: { ready: boolean }) {
  const fill = useFillHeight<HTMLDivElement>({ min: 100, gap: 10 })
  if (!ready) return <p>불러오는 중</p>
  return <div data-testid="box" ref={fill.ref} style={fill.style} />
}

function inMain(ready: boolean) {
  return (
    <main>
      <Late ready={ready} />
    </main>
  )
}

describe('useFillHeight', () => {
  it('조기 반환 뒤에 나타난 요소도 붙는 순간 잰다', () => {
    const { container, rerender } = render(inMain(false))
    const main = container.querySelector('main')!
    Object.defineProperty(main, 'clientHeight', { configurable: true, value: 1000 })

    rerender(inMain(true))

    // 예전에는 여기서 바닥값(100)에 머물렀다 — 첫 측정 때 요소가 없어 건너뛰고, 그 뒤로
    // deps 가 안 바뀌어 다시 재지 않았다. 사람에게는 「누르면 늘고 다시 열면 줄어든다」 였다.
    expect(screen.getByTestId('box').style.height).toBe('990px')
  })

  it('남는 자리가 바닥값보다 작으면 바닥값을 지킨다', () => {
    const { container, rerender } = render(inMain(false))
    const main = container.querySelector('main')!
    Object.defineProperty(main, 'clientHeight', { configurable: true, value: 50 })

    rerender(inMain(true))

    expect(screen.getByTestId('box').style.height).toBe('100px')
  })
})
