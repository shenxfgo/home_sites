/**
 * 提示文案的语言闸门（#131）。
 *
 * 全站界面文案是中文的，唯独 `ElMessage` 那一批有 17 处整句英文开头（`Failed to load tags: …`、
 * `Operation failed: …`、`Delete failed: …`），夹在同一张卡片上的「标签已创建」和「删除标签失败」
 * 之间。这不是一处笔误，是一族，而且它会自己长新的：#74 那一批 catch 是照着 axios 的英文报错写的，
 * 谁再补一个 catch 就照抄邻居。所以这里钉的是**这一族**，不是那 17 条串。
 *
 * 为什么必须再来一层静态的：这 17 处文案改回英文不会有任何一条用例红。单测断的是
 * `toHaveBeenCalledWith(expect.stringContaining('服务端那句原因'))`（前缀压根不在断言里），
 * e2e 断的也是那句原因——两层都在核"服务端原话有没有被吞"，没有一层核"那句话外面套的是哪种语言"。
 */
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), '../../src')

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) return sourceFiles(full)
    return /\.(ts|vue)$/.test(entry.name) ? [full] : []
  })
}

/**
 * 一处调用连着它的第一个实参：方法名限定在这六个上，引号类型跟着捕获，内容取到下一个同种
 * 引号为止（跨行的 `ElMessageBox.confirm(` 因此也进得来）。模板里的 `${...}` 被截断没关系——
 * 这条规则问的是"这句话里有没有中文"，整句英文的串后面插什么都不会因此变中文。
 */
const CALL =
  /ElMessage(?:Box)?\.(error|success|warning|info|confirm|prompt)\(\s*(['"`])([\s\S]*?)\2/g

const CJK = /[一-鿿]/

/**
 * 注释里的 `ElMessage.error('Failed: …')` 只是文档句，得先刮掉再比（同 #123 那条规矩）。
 * 刮的时候保留换行，否则后面每一条的行号都会往回跳，清单就指不到人脸上了。
 */
function codeOnly(text: string): string {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, (block) => block.replace(/[^\n]/g, ' '))
    .replace(/<!--[^\n]*-->/g, (block) => block.replace(/[^\n]/g, ' '))
    .replace(/\/\/[^\n]*/g, (line) => line.replace(/[^\n]/g, ' '))
}

interface Toast {
  where: string
  call: string
  chinese: boolean
}

function toasts(text: string, file: string): Toast[] {
  const found: Toast[] = []
  for (const match of text.matchAll(CALL)) {
    const start = match.index ?? 0
    found.push({
      where: `${file.slice(SRC.length + 1)}:${text.slice(0, start).split('\n').length}`,
      call: match[0].replace(/\s+/g, ' ').trim(),
      chinese: CJK.test(match[3] ?? ''),
    })
  }
  return found
}

describe('toast copy language', () => {
  const files = sourceFiles(SRC)
  const examined = files.flatMap((file) => toasts(codeOnly(readFileSync(file, 'utf-8')), file))

  it('scans a real set of source files', () => {
    // 目录走错一步就是「零处文案、零处违规」的全绿，先把扫描本身钉住（同 #123 的闸门）。
    expect(files.length).toBeGreaterThanOrEqual(40)
  })

  it('examines every toast the app can show', () => {
    // 正则写坏同样是「一处都没看到」的绿——这条下限就是给正则自己用的。
    // 实测基线：`src/` 里 ElMessage 88 处 + ElMessageBox 12 处。
    expect(examined.length).toBeGreaterThanOrEqual(60)
  })

  it('never opens a message with an English sentence', () => {
    const offenders = examined.filter((t) => !t.chinese).map((t) => `${t.where} ${t.call}`)
    expect(offenders).toEqual([])
  })
})
