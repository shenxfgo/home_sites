import { describe, expect, it } from 'vitest'
import { isTypingTarget } from '@/composables/typingGuard'

/** Build a detached element from markup, the way a browser would hand it to a key event. */
function build(html: string): HTMLElement {
  const host = document.createElement('div')
  host.innerHTML = html
  return host.firstElementChild as HTMLElement
}

describe('isTypingTarget', () => {
  it('steps aside for every kind of field', () => {
    expect(isTypingTarget(build('<input>'))).toBe(true)
    expect(isTypingTarget(build('<textarea></textarea>'))).toBe(true)
    expect(isTypingTarget(build('<select></select>'))).toBe(true)
    expect(isTypingTarget(build('<select><option>a</option></select>').firstElementChild as HTMLElement)).toBe(true)
  })

  it('steps aside for a key typed into a rich text box', () => {
    const box = build('<div></div>')
    Object.defineProperty(box, 'isContentEditable', { value: true })

    expect(isTypingTarget(box)).toBe(true)
  })

  it('lets the page keep the key otherwise', () => {
    expect(isTypingTarget(document.body)).toBe(false)
    expect(isTypingTarget(build('<p>hi</p>'))).toBe(false)
    expect(isTypingTarget(null)).toBe(false)
    expect(isTypingTarget(new EventTarget())).toBe(false)
  })
})
