import type { VueWrapper } from '@vue/test-utils'
import type { MessageBoxData } from 'element-plus'

/** Element Plus types the confirm result as an object/string intersection that no literal satisfies. */
export const CONFIRMED = { value: '', action: 'confirm' } as unknown as MessageBoxData

/** Find a rendered button by the text it shows. */
export function buttonByText<T>(wrapper: VueWrapper<T>, label: string) {
  const found = wrapper.findAll('button').find((node) => node.text().includes(label))
  if (!found) throw new Error(`找不到文案包含 "${label}" 的按钮`)
  return found
}

/** Find a raw DOM button outside the wrapper, e.g. inside a teleported popover. */
export function domButtonByText(root: ParentNode | null | undefined, label: string) {
  return Array.from(root?.querySelectorAll('button') ?? []).find((node) =>
    node.textContent?.includes(label),
  )
}
