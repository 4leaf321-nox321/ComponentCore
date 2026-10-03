import { saveRecipeAs } from '@/modules/cad/download'

test('전개도는 펴기 길로 DXF 를 받아 「이름-전개도.dxf」 로 내려받는다', async () => {
  const urls: string[] = []
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    urls.push(String(input))
    return new Response('0\nSECTION', { status: 200, headers: { 'Content-Type': 'application/dxf' } })
  })
  const clicked: string[] = []
  const realCreate = document.createElement.bind(document)
  vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
    const element = realCreate(tag)
    if (tag === 'a') element.click = () => clicked.push((element as HTMLAnchorElement).download)
    return element
  })
  URL.createObjectURL = vi.fn(() => 'blob:x')
  URL.revokeObjectURL = vi.fn()
  await saveRecipeAs({ nodes: [] }, 'flat', '브래킷')
  expect(urls[0]).toContain('/cad/recipe/unfold?format=dxf')
  expect(clicked).toEqual(['브래킷-전개도.dxf'])
})
