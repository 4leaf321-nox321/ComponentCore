import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { Link, RouterProvider, createMemoryRouter, useParams } from 'react-router-dom'
import type { RouteObject } from 'react-router-dom'

import { useTabActive } from '@/shared/layout/tabActive'
import { MAX_TABS, TabBar, TabPanes, TabsProvider, menuLabel, useTabTitle, useTabs } from '@/shared/layout/tabs'

// 화면 탭(2026-11-17) — 탭마다 화면이 살아 있고, 보이는 탭이 주소를 따른다.

/** 손으로 바꾼 상태 — 탭을 오가도 남아야 한다(조립에서 고치던 배치처럼). */
function Counter() {
  const [count, setCount] = useState(0)
  const active = useTabActive()
  return (
    <div>
      <button type="button" onClick={() => setCount(count + 1)}>
        더하기 {count}
      </button>
      <span>{active ? 'A 보임' : 'A 숨음'}</span>
      <Link to="/b/9">부품 9로</Link>
    </div>
  )
}

function Part() {
  const { id } = useParams()
  useTabTitle(`부품 ${id}`)
  return <p>부품 화면 {id}</p>
}

const routes: RouteObject[] = [
  { path: 'a', element: <Counter /> },
  { path: 'b/:id', element: <Part /> },
]

let opened: boolean | null = null
let next = 100
function Opener() {
  const tabs = useTabs()!
  return (
    <>
      <button type="button" onClick={() => (opened = tabs.open('/b/7', '받침'))}>
        탭으로 열기
      </button>
      <button type="button" onClick={() => (opened = tabs.open(`/b/${(next += 1)}`))}>
        다른 탭 열기
      </button>
    </>
  )
}

function Shell() {
  return (
    <TabsProvider>
      <TabBar />
      <Opener />
      <main>
        <TabPanes routes={routes} fallback={null} />
      </main>
    </TabsProvider>
  )
}

function show(path = '/a') {
  const router = createMemoryRouter([{ path: '/', element: <Shell />, children: routes }], { initialEntries: [path] })
  render(<RouterProvider router={router} />)
  return router
}

beforeEach(() => {
  sessionStorage.clear()
  opened = null
})

test('탭으로 연 화면에 다녀와도 앞 탭의 상태가 그대로다', async () => {
  const router = show()
  // 탭이 하나면 탭 줄이 없다.
  expect(screen.queryByRole('tablist')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '더하기 0' }))
  fireEvent.click(screen.getByRole('button', { name: '탭으로 열기' }))
  expect(opened).toBe(true)
  expect(await screen.findByText('부품 화면 7')).toBeVisible()
  expect(router.state.location.pathname).toBe('/b/7')
  // 앞 탭은 숨었을 뿐 살아 있다 — 단축키 · 3D 는 쉰다.
  expect(screen.getByText('A 숨음')).not.toBeVisible()
  const tabs = screen.getAllByRole('tab')
  // 화면이 이름을 주면 그것(부품 7), 탭을 열 때 준 이름은 그 전까지.
  expect(tabs.map((one) => one.textContent)).toEqual(['/a', '부품 7'])
  expect(tabs[1]).toHaveAttribute('aria-selected', 'true')

  fireEvent.click(tabs[0])
  expect(router.state.location.pathname).toBe('/a')
  expect(screen.getByRole('button', { name: '더하기 1' })).toBeVisible()
  expect(screen.getByText('A 보임')).toBeInTheDocument()

  // 같은 주소를 다시 열면 새 탭을 만들지 않고 그리로 간다.
  fireEvent.click(screen.getByRole('button', { name: '탭으로 열기' }))
  expect(screen.getAllByRole('tab')).toHaveLength(2)
  expect(router.state.location.pathname).toBe('/b/7')

  fireEvent.click(screen.getByRole('button', { name: '부품 7 탭 닫기' }))
  expect(screen.queryByRole('tablist')).toBeNull()
  expect(router.state.location.pathname).toBe('/a')
  expect(screen.getByRole('button', { name: '더하기 1' })).toBeVisible()
})

test('보이는 탭이 주소를 따른다 — 링크로 옮기면 지금 탭이 그 화면이 된다', async () => {
  const router = show()
  fireEvent.click(screen.getByRole('button', { name: '탭으로 열기' }))
  fireEvent.click(screen.getAllByRole('tab')[0])
  fireEvent.click(screen.getByRole('link', { name: '부품 9로' }))
  expect(await screen.findByText('부품 화면 9')).toBeVisible()
  expect(router.state.location.pathname).toBe('/b/9')
  expect(screen.getAllByRole('tab').map((one) => one.textContent)).toEqual(['부품 9', '부품 7'])
})

test('새로 고쳐도 탭이 남고, 남은 탭은 누를 때 그린다', async () => {
  const first = show()
  fireEvent.click(screen.getByRole('button', { name: '탭으로 열기' }))
  expect(first.state.location.pathname).toBe('/b/7')
  // 다시 연다(새로 고침) — 주소는 /b/7.
  document.body.innerHTML = ''
  const again = show('/b/7')
  expect(screen.getAllByRole('tab').map((one) => one.getAttribute('aria-selected'))).toEqual(['false', 'true'])
  expect(screen.queryByRole('button', { name: /더하기/ })).toBeNull() // 앞 탭은 아직 안 그렸다
  fireEvent.click(screen.getAllByRole('tab')[0])
  expect(again.state.location.pathname).toBe('/a')
  expect(await screen.findByRole('button', { name: '더하기 0' })).toBeVisible()
})

test('탭 수에는 상한이 있다 — 3D 가 탭마다 WebGL 문맥을 쥔다', () => {
  show()
  for (let n = 1; n < MAX_TABS; n += 1) fireEvent.click(screen.getByRole('button', { name: '다른 탭 열기' }))
  expect(screen.getAllByRole('tab')).toHaveLength(MAX_TABS)
  fireEvent.click(screen.getByRole('button', { name: '다른 탭 열기' }))
  expect(opened).toBe(false)
  expect(screen.getAllByRole('tab')).toHaveLength(MAX_TABS)
})

test('화면이 이름을 안 주면 메뉴 이름 — 주소의 가장 긴 앞부분', () => {
  expect(menuLabel('/works/abc')).toBe('내 작업')
  expect(menuLabel('/assemblies/x?y=1')).toBe('조립')
  expect(menuLabel('/nowhere')).toBe('/nowhere')
})
