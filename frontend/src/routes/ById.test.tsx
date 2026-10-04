import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'

import { ById } from '@/routes/ById'

function Page() {
  const [picked, setPicked] = useState('없음')
  return (
    <div>
      <p>고른 버전: {picked}</p>
      <button type="button" onClick={() => setPicked('v3')}>
        v3 고르기
      </button>
      <Link to="/works/b">다른 작업</Link>
    </div>
  )
}

test('주소의 id 가 바뀌면 앞 작업의 상태를 들고 있지 않는다', () => {
  render(
    <MemoryRouter initialEntries={['/works/a']}>
      <Routes>
        <Route
          path="/works/:id"
          element={
            <ById>
              <Page />
            </ById>
          }
        />
      </Routes>
    </MemoryRouter>,
  )
  fireEvent.click(screen.getByRole('button', { name: 'v3 고르기' }))
  expect(screen.getByText('고른 버전: v3')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('link', { name: '다른 작업' }))
  expect(screen.getByText('고른 버전: 없음')).toBeInTheDocument()
})
