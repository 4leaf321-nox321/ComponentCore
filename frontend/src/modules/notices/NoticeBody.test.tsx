/**
 * 공지 본문 — 한 줄 안의 `**굵게**` · `` `코드` `` 만 그린다.
 *
 *   줄을 넘는 짝은 글자 그대로 — 사이 글이 통째로 `**` 로 시작하고 끝나도 굵게 그리지 않는다
 *   HTML 은 글자로 나온다
 */

import { render } from '@testing-library/react'

import { NoticeBody } from '@/modules/notices/NoticeBody'

function html(text: string) {
  const { container } = render(<NoticeBody text={text} />)
  return container.firstElementChild!
}

describe('공지 본문', () => {
  it('한 줄 안의 굵게 · 코드를 그린다', () => {
    const body = html('**바뀐 것** — `units=si` 를 붙이세요.')
    expect(body.querySelector('strong')?.textContent).toBe('바뀐 것')
    expect(body.querySelector('code')?.textContent).toBe('units=si')
    expect(body.textContent).toBe('바뀐 것 — units=si 를 붙이세요.')
  })

  it('줄을 넘는 짝은 글자 그대로 둔다', () => {
    for (const text of ['**한 줄\n다음 줄**', '`한 줄\n다음 줄`', '앞 **굵게** 뒤\n**넘는\n짝**']) {
      const body = html(text)
      expect(body.querySelectorAll('code')).toHaveLength(0)
      expect([...body.querySelectorAll('strong')].map((one) => one.textContent)).toEqual(
        text.startsWith('앞') ? ['굵게'] : []
      )
      expect(body.textContent).toBe(text.replace('**굵게**', '굵게'))
    }
  })

  it('HTML 과 짝 없는 표기는 글자로 나온다', () => {
    const body = html('<b>x</b> ` 하나 ****')
    expect(body.querySelector('b')).toBeNull()
    expect(body.textContent).toBe('<b>x</b> ` 하나 ****')
  })
})
