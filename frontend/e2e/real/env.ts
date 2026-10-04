/**
 * 真后端 e2e 的接线常量：端口、一次性目录、以及测试库的连接串。
 *
 * 连接串里带着 app 角色的口令，所以它**只进被启动进程的环境变量**，从不进 argv、
 * 从不打印：播种脚本的 stdout 只回库名，uvicorn 也只日志它自己的行。
 */
import { readFileSync, existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))

/** 一次性后端监听的端口。刻意避开 8000——那是开发者手动起的进程，撞上去就等于拿真库当靶子。 */
export const API_PORT = 8099

/** 这一套用的 Vite 端口。4173 是替身 e2e 在用的，两边同时跑也互不复用。 */
export const APP_PORT = 4174

export const BACKEND_DIR = resolve(HERE, '../../../backend')

/** 媒体、封面都落在 gitignored 的 data/ 下面，跑完可以整个删掉。 */
export const E2E_DIR = resolve(BACKEND_DIR, 'data/e2e')
export const MEDIA_DIR = resolve(E2E_DIR, 'media')
export const THUMBNAIL_DIR = resolve(E2E_DIR, 'thumbnails')

export const E2E_USERNAME = 'e2e_owner'

/**
 * 测试账号的口令，字面值进版本库。它不构成凭据：这个库的名字必须以 `_test` 结尾才允许
 * 被清空（闸门在 `backend/src/e2e_seed.py`），而且每次跑之前整表 TRUNCATE。
 */
export const E2E_PASSWORD = 'e2e-only-password'

/** 后端 venv 里的 python 可执行文件，按平台拼。 */
export function pythonPath(): string {
  const bin = process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'
  return resolve(BACKEND_DIR, '.venv', bin)
}

/** 从 backend/.env 里取一条键值；文件里的值是最后一行为准，和环境变量同名时环境变量优先。 */
function fromEnvFile(key: string): string | null {
  const file = resolve(BACKEND_DIR, '.env')
  if (!existsSync(file)) return null
  let value: string | null = null
  for (const line of readFileSync(file, 'utf8').split(/\r?\n/)) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const split = trimmed.indexOf('=')
    if (split <= 0) continue
    if (trimmed.slice(0, split).trim().toLowerCase() !== key.toLowerCase()) continue
    value = trimmed.slice(split + 1).trim().replace(/^["']|["']$/g, '')
  }
  return value
}

/**
 * e2e 用哪个库。出处是 backend/.env 的 TEST_DATABASE_URL，也可以用 E2E_DATABASE_URL
 * 临时覆盖。只接受 PostgreSQL：这套用例存在的理由之一就是证明真库那一侧的契约。
 */
export function testDatabaseUrl(): string {
  const url = process.env.E2E_DATABASE_URL ?? fromEnvFile('TEST_DATABASE_URL') ?? ''
  if (!url.startsWith('postgresql')) {
    throw new Error(
      'real-backend e2e needs a PostgreSQL test database. Set TEST_DATABASE_URL in ' +
        'backend/.env (or E2E_DATABASE_URL) to e.g. postgresql+asyncpg://…/home_sites_test.',
    )
  }
  if (!url.split('/').pop()?.endsWith('_test')) {
    throw new Error(`refusing to run e2e against ${url.split('/').pop()}: the database name must end in _test`)
  }
  return url
}

/**
 * 一次性后端进程的环境：连接串指向测试库，封面写进一次性目录，每日备份关掉。
 *
 * 备份那条不是可选项——这个进程连的是真方言，不关掉它就会在凌晨挂着一份读不回来的
 * 测试库快照，还往共享的备份目录里写文件。
 */
export function backendEnv(extra: Record<string, string> = {}): Record<string, string> {
  return {
    ...(process.env as Record<string, string>),
    DATABASE_URL: testDatabaseUrl(),
    THUMBNAIL_PATH: THUMBNAIL_DIR,
    BACKUP_ENABLED: 'false',
    PYTHONIOENCODING: 'utf-8',
    ...extra,
  }
}
