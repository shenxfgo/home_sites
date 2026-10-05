import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join, resolve, sep } from 'node:path'
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

/** 只有默认导入才是「拿到 axios 实例、可以就地拼 URL」；router 那个具名导入不发请求。 */
const DEFAULT_CLIENT_IMPORT = /^import\s+[\w$]+\s*(?:,\s*\{[^}]*\})?\s*from\s+['"][^'"]*client['"]/m

describe('requests built outside src/api/', () => {
  const outside = sourceFiles(SRC).filter((file) => !file.includes(`${sep}api${sep}`))

  it('scan a real set of source files', () => {
    // 目录走错一步就是「零个文件、零个违规」的全绿，先把扫描本身钉住。
    expect(outside.length).toBeGreaterThanOrEqual(25)
  })

  it('keeps every request inside an api module, where the route table can check it', () => {
    const offenders = outside
      .filter((file) => DEFAULT_CLIENT_IMPORT.test(readFileSync(file, 'utf-8')))
      .map((file) => file.slice(SRC.length + 1))
    expect(offenders).toEqual([])
  })
})
