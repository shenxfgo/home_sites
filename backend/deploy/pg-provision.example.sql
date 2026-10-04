-- PostgreSQL 建库模板（home_sites）
--
-- 用法：把下面两处 __REPLACE_ME__ 换成一个真口令，**换成之后的那份不要提交**
-- （留在 backend/data/ 里就行，那目录已经整目录 gitignore）。这个模板进版本库，
-- 里面永远不该有口令——它能重建库，不需要知道任何一台机器上库的口令。
--
-- 需要一个能建角色的高权限账号（默认 superuser `postgres`），在本机执行：
--   "D:/Program Files/PostgreSQL/18/bin/psql.exe" -U postgres -h 127.0.0.1 \
--       -f backend/deploy/pg-provision.example.sql
-- 或者先另存一份替换好口令的副本，再 `-f` 那份副本；两种都要在本机跑，
-- 口令不经过任何网络。
--
-- 跑完之后：把连接串按 `postgresql+asyncpg://home_sites_app:<口令>@127.0.0.1:5432/home_sites`
-- 写进 backend/.env 的 DATABASE_URL（测试库另填 TEST_DATABASE_URL）。表结构不在这里建，
-- 由 Alembic 基线在首次启动时建（见 backend/alembic/）。

-- 如果角色已经存在，下面这句会让整个脚本中止；改用这句，然后注释掉 CREATE ROLE：
-- ALTER ROLE home_sites_app PASSWORD '__REPLACE_ME__';
CREATE ROLE home_sites_app LOGIN PASSWORD '__REPLACE_ME__';

-- 只有 LOGIN：不建库、不建角色、不是超管。两个库的 OWNER 都是它，所以它对自己的
-- public schema 有 CREATE（PostgreSQL 15+ 的 pg_database_owner 规则），Alembic 建表
-- 不需要额外 GRANT。
--
-- LOCALE 'C' 是有意的：C 就是 UTF-8 字节序，和 SQLite 一直在用的 BINARY 排序一致。
-- 换成 ICU/libc 的本地规则，切换当天整个片库的 ORDER BY title 会静默重排一遍。
CREATE DATABASE home_sites
    OWNER home_sites_app
    TEMPLATE template0
    LOCALE_PROVIDER libc
    LC_COLLATE 'C'
    LC_CTYPE 'C'
    ENCODING 'UTF8';

-- 测试专用库：整套用例在设了 TEST_DATABASE_URL 时跑在这里，真库数据不受影响。
CREATE DATABASE home_sites_test
    OWNER home_sites_app
    TEMPLATE template0
    LOCALE_PROVIDER libc
    LC_COLLATE 'C'
    LC_CTYPE 'C'
    ENCODING 'UTF8';

-- 建完自查：两个库都该是 C / C / UTF8，且都归 home_sites_app。
SELECT datname, datcollate, datctype, pg_encoding_to_char(encoding) AS encoding
  FROM pg_database
 WHERE datname LIKE 'home_sites%'
 ORDER BY datname;
