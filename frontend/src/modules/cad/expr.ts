/**
 * 변수 식 풀기 — **미리보기용**.
 *
 * 정본은 서버다(`core/recipe/params.py`). 여기서 다시 푸는 이유는 하나뿐이다: 스케치 캔버스가
 * `"=판_길이"` 를 그대로 그릴 수 없기 때문이다. `Number("=판_길이")` 는 NaN 이고, 그러면 도형이
 * 화면에서 사라진다 — 값을 쓴 사람은 자기가 무엇을 만들었는지 못 본다.
 *
 * 문법은 서버와 **같은 것만** 받는다: 이름 · 숫자 · `+ - * / % **` · 괄호 · 흰 목록 함수.
 * 못 풀면 NaN 을 돌려주고, 화면은 그 칸을 비워 둔다 — 틀린 값을 그럴듯하게 그리지 않는다.
 */

const FUNCTIONS: Record<string, (...args: number[]) => number> = {
  abs: Math.abs,
  min: Math.min,
  max: Math.max,
  round: Math.round,
  sqrt: Math.sqrt,
  sin: (deg) => Math.sin((deg * Math.PI) / 180),
  cos: (deg) => Math.cos((deg * Math.PI) / 180),
  tan: (deg) => Math.tan((deg * Math.PI) / 180),
  hypot: Math.hypot,
}
const CONSTANTS: Record<string, number> = { pi: Math.PI }

/** 못 푼 까닭 — 화면이 **무엇을 고치면 되는지** 말할 수 있게 나눠 준다. */
export type Trouble =
  /** 아직 아무것도 안 썼다(`=`). 틀린 것이 아니라 **쓰는 중**이다. */
  | { kind: 'empty'; message: string }
  /** 그런 변수가 없다. 이름을 고치거나 **그 이름으로 만들면** 된다. */
  | { kind: 'unknown'; name: string; message: string }
  /** 괄호가 안 닫혔거나 연산자가 남았다 — 대개 쓰는 도중이다. */
  | { kind: 'syntax'; message: string }

class UnknownName extends Error {
  readonly name: string

  constructor(name: string) {
    super(`모르는 변수: ${name}`)
    this.name = name
  }
}

export function isExpression(value: unknown): value is string {
  return typeof value === 'string' && value.startsWith('=')
}

/** 값을 숫자로. 식이면 풀고, 못 풀면 NaN. */
export function evalNumber(value: unknown, params: Record<string, number> = {}): number {
  if (typeof value === 'number') return value
  if (!isExpression(value)) return Number(value)
  try {
    const parser = new Parser(value.slice(1), params)
    const got = parser.expression()
    parser.expectEnd()
    return got
  } catch {
    return Number.NaN
  }
}

/** 못 푼 까닭. 풀리면 null. */
export function explain(value: unknown, params: Record<string, number> = {}): Trouble | null {
  if (!isExpression(value)) return null
  const body = value.slice(1).trim()
  if (body === '') return { kind: 'empty', message: '식을 쓰세요 — 예: 두께 * 2' }
  try {
    const parser = new Parser(body, params)
    parser.expression()
    parser.expectEnd()
    return null
  } catch (caught) {
    if (caught instanceof UnknownName) {
      return {
        kind: 'unknown',
        name: caught.name,
        message: `「${caught.name}」 이라는 변수가 없습니다`,
      }
    }
    return { kind: 'syntax', message: '식을 읽을 수 없습니다 — 괄호와 연산자를 보세요' }
  }
}

/** 화면에 보여 줄 값 — 못 풀면 빈 문자열(「NaN」 을 보여 주지 않는다). */
export function resolvedText(value: unknown, params: Record<string, number> = {}): string {
  const got = evalNumber(value, params)
  if (!Number.isFinite(got)) return ''
  return String(Math.round(got * 1000) / 1000)
}

/** 재귀 하향 파서 — 연산자 우선순위는 서버(파이썬)와 같다. */
class Parser {
  private at = 0
  private readonly text: string
  private readonly params: Record<string, number>

  constructor(text: string, params: Record<string, number>) {
    this.text = text
    this.params = params
  }

  expectEnd() {
    this.skip()
    if (this.at < this.text.length) throw new Error('남은 글자')
  }

  expression(): number {
    let left = this.term()
    for (;;) {
      this.skip()
      const op = this.text[this.at]
      if (op !== '+' && op !== '-') return left
      this.at += 1
      const right = this.term()
      left = op === '+' ? left + right : left - right
    }
  }

  private term(): number {
    let left = this.power()
    for (;;) {
      this.skip()
      const op = this.text[this.at]
      if (op !== '*' && op !== '/' && op !== '%') return left
      if (op === '*' && this.text[this.at + 1] === '*') return left // ** 는 power 가 본다
      this.at += 1
      const right = this.power()
      left = op === '*' ? left * right : op === '/' ? left / right : left % right
    }
  }

  private power(): number {
    const base = this.unary()
    this.skip()
    if (this.text.startsWith('**', this.at)) {
      this.at += 2
      return base ** this.power() // 오른쪽 결합
    }
    return base
  }

  private unary(): number {
    this.skip()
    const sign = this.text[this.at]
    if (sign === '-' || sign === '+') {
      this.at += 1
      const got = this.unary()
      return sign === '-' ? -got : got
    }
    return this.atom()
  }

  private atom(): number {
    this.skip()
    const char = this.text[this.at]
    if (char === '(') {
      this.at += 1
      const got = this.expression()
      this.skip()
      if (this.text[this.at] !== ')') throw new Error('괄호가 안 닫혔습니다')
      this.at += 1
      return got
    }
    const number = /^\d+(\.\d+)?/.exec(this.text.slice(this.at))
    if (number) {
      this.at += number[0].length
      return Number(number[0])
    }
    // 이름 — **한글도 쓴다.** 자바스크립트의 `\w` 는 ASCII 뿐이라(파이썬과 다르다) 유니코드
    // 글자 속성으로 받는다. 이것을 놓치면 「=판_길이」 가 캔버스에서만 안 풀린다.
    const name = /^[\p{L}_][\p{L}\p{N}_]*/u.exec(this.text.slice(this.at))
    if (!name) throw new Error('읽을 수 없습니다')
    this.at += name[0].length
    this.skip()
    if (this.text[this.at] === '(') {
      const fn = FUNCTIONS[name[0]]
      if (!fn) throw new Error('모르는 함수')
      this.at += 1
      const args: number[] = []
      for (;;) {
        args.push(this.expression())
        this.skip()
        if (this.text[this.at] === ',') {
          this.at += 1
          continue
        }
        break
      }
      if (this.text[this.at] !== ')') throw new Error('괄호가 안 닫혔습니다')
      this.at += 1
      return fn(...args)
    }
    if (name[0] in this.params) return this.params[name[0]]
    if (name[0] in CONSTANTS) return CONSTANTS[name[0]]
    throw new UnknownName(name[0])
  }

  private skip() {
    while (this.at < this.text.length && /\s/.test(this.text[this.at])) this.at += 1
  }
}
