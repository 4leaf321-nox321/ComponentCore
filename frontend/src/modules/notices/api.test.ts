/**
 * 읽음을 적는 함수가 **직접 알린다** — 사이드바의 수(`refreshNavBadges`)가 곧바로 다시 센다.
 * 읽음을 적는 자리가 여럿이라(상세 · 로그인 팝업 · 「모두 읽음」) 화면마다 알리게 두면 한 곳은 빠진다.
 */

import { noticesApi } from '@/modules/notices/api'

const post = vi.fn()
const refresh = vi.fn()

vi.mock('@/shared/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/shared/api/client')>()
  return { ...actual, api: { ...actual.api, post: (...args: unknown[]) => post(...args) } }
})

vi.mock('@/shared/api/navBadges', () => ({ refreshNavBadges: () => refresh() }))

beforeEach(() => vi.clearAllMocks())

test('한 건을 읽으면 수를 다시 센다', async () => {
  post.mockResolvedValue(undefined)
  await noticesApi.read('n1')
  expect(post).toHaveBeenCalledWith('/notices/n1/read')
  expect(refresh).toHaveBeenCalledTimes(1)
})

test('모두 읽음도 다시 세고, 서버의 답을 그대로 돌려준다', async () => {
  post.mockResolvedValue({ unread: 0 })
  await expect(noticesApi.readAll()).resolves.toEqual({ unread: 0 })
  expect(refresh).toHaveBeenCalledTimes(1)
})

test('실패하면 다시 세지 않는다 — 안 읽은 채인데 수만 다시 세게 하지 않는다', async () => {
  post.mockRejectedValue(new Error('끊김'))
  await expect(noticesApi.read('n1')).rejects.toThrow('끊김')
  expect(refresh).not.toHaveBeenCalled()
})
