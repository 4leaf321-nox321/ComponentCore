import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'

import { NumberText } from '@/modules/conditions/NumberText'

function Harness({ seen }: { seen: { value: unknown } }) {
  const [value, setValue] = useState<unknown>(null)
  seen.value = value
  return (
    <>
      <NumberText aria-label="요소 크기" value={value} onText={(text) => setValue(text === '' ? null : Number(text))} />
      <button type="button" onClick={() => setValue(null)}>
        초기화
      </button>
    </>
  )
}

test('소수를 한 글자씩 칠 수 있고, 바깥에서 바뀌면 따라간다', () => {
  const seen = { value: null as unknown }
  render(<Harness seen={seen} />)
  const box = screen.getByLabelText('요소 크기')
  // 「0.」 에서 0 으로 되그려지면 다음 글자를 칠 수 없었다.
  for (const text of ['0', '0.', '0.5']) fireEvent.change(box, { target: { value: text } })
  expect(box).toHaveValue('0.5')
  expect(seen.value).toBe(0.5)
  fireEvent.change(box, { target: { value: '1.' } })
  expect(box).toHaveValue('1.')
  fireEvent.click(screen.getByRole('button', { name: '초기화' }))
  expect(box).toHaveValue('')
})
