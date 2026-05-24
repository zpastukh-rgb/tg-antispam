import { describe, expect, it } from 'vitest'
import {
  draftsToParsed,
  parseQuestionsText,
  parsedToDrafts,
  questionsToText,
} from './joinRequestsQuestionsForm.js'

describe('joinRequestsQuestionsForm', () => {
  it('parses Q/A/B like backend', () => {
    const raw = `Q: Прочитайте правила
A: понимаю
B: Правила=https://t.me/rules&&Канал=https://t.me/channel

Q: Число
A: 3; 5; 7`
    const qs = parseQuestionsText(raw)
    expect(qs).toHaveLength(2)
    expect(qs[0].answers).toEqual(['понимаю'])
    expect(qs[0].buttons[0]).toHaveLength(2)
    expect(qs[1].answers).toEqual(['3', '5', '7'])
  })

  it('roundtrips through draft UI', () => {
    const raw = 'Q: One\nA: a; b\n\nQ: Two\nA: c'
    const drafts = parsedToDrafts(parseQuestionsText(raw))
    expect(drafts[0].answersText).toBe('a, b')
    const back = questionsToText(draftsToParsed(drafts))
    const qs2 = parseQuestionsText(back)
    expect(qs2).toHaveLength(2)
    expect(qs2[0].answers).toEqual(['a', 'b'])
  })
})
