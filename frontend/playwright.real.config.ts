import { defineConfig, devices } from '@playwright/test'
import {
  API_PORT,
  APP_PORT,
  BACKEND_DIR,
  E2E_PASSWORD,
  MEDIA_DIR,
  backendEnv,
  pythonPath,
  testDatabaseUrl,
} from './e2e/real/env'

// 这个文件里的顶层代码会被**执行好几遍**（主进程一次，每个 worker 再各一次；本机实测
// 三个进程），所以除了读配置的只读检查，什么都不许放在这里。往媒体目录写文件曾经是
// 放在这里的——于是播种之后又被清了一次，封面路径指向一个不存在的文件。夹具的准备现在
// 归 backend/src/e2e_seed.py，它和扫描在同一条顺序执行的链里。

// 连接串拿不到就别启动任何东西——两个服务器起来再失败，日志里看到的是端口问题而不是
// "你没配测试库"。
testDatabaseUrl()

const PY = `"${pythonPath()}"`

export default defineConfig({
  testDir: './e2e/real',
  testMatch: '**/*.real.spec.ts',
  // 一条播种链喂着所有用例：大家共用同一个库，而且有用例会自己往库里新写一行（片单
  // 那条要新建一条片单），所以既不能并发、也不能单独调换顺序——一次 e2e 也就十几秒。
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: `http://localhost:${APP_PORT}`,
    trace: 'retain-on-failure',
    locale: 'zh-CN',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      // 造媒体 → 清库并扫描 → 成功之后才起服务。顺序由这条 && 保证，不靠夹具的时机。
      command: `${PY} -m src.e2e_seed && ${PY} -m uvicorn src.main:app --host 127.0.0.1 --port ${API_PORT}`,
      cwd: BACKEND_DIR,
      env: backendEnv({ E2E_PASSWORD, E2E_MEDIA_DIR: MEDIA_DIR }),
      url: `http://127.0.0.1:${API_PORT}/health`,
      // 绝不复用：8000 上是开发者手动起的进程，拿它跑 e2e 等于往真库里写测试数据。
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `npm run dev -- --port ${APP_PORT} --strictPort`,
      env: { E2E_API_TARGET: `http://127.0.0.1:${API_PORT}` },
      url: `http://localhost:${APP_PORT}`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
})
