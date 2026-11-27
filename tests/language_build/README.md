# GitBook 语言目录构建验证

1. **范围**

   此目录提供第一阶段的验证样例，现与仓库模板共用路径后处理脚本。
   脚本仅创建新的测试目录，不修改、自动迁移或发布真实站点。

   验证四组站点：

   | 样例 | 源码结构 | 最终公开路径 |
   | --- | --- | --- |
   | `legacy` | 根目录首页、导航、文章 | `/`、`/articles/…` |
   | `new-single` | `LANGS.md` + `zh-hans/` | 与单语言旧结构相同 |
   | `added-language` | 原中文目录不动，新增 `en/` | 原地址不变，新增 `/en/…` |
   | `migrated-legacy` | 将旧样例内容完整复制到 `zh-hans/`，新增 `en/` | 原地址不变，新增 `/en/…` |

   迁移只操作合成样例中明确列出的内容；这不是可直接对任意旧仓库运行的迁移器。

2. **运行环境**

   使用与现有 CI 相同的 Node.js 10.24.1、GitBook CLI 2.3.2、GitBook 3.2.3，以及 Python 3、Make。
   首次安装依赖需要 npm 网络访问；已有依赖后，本地构建不需要 Seenical 服务或管理凭据。
   样例使用实际模板插件，替换业务网址和统计标识，不将真实管理凭据带入产物。

   在仓库根目录运行以下命令。若已安装相同版本的 GitBook，可跳过临时运行环境的安装。

   ```bash
   nvm use 10.24.1
   gitbook_lab="$(mktemp -d /tmp/gitbook-language-build.XXXXXX)"
   npm install --prefix "$gitbook_lab/runtime" gitbook@3.2.3 gitbook-cli@2.3.2 --no-audit --no-fund
   export GITBOOK_DIR="$gitbook_lab/cache"
   mkdir -p "$GITBOOK_DIR/versions"
   ln -s "$gitbook_lab/runtime/node_modules/gitbook" "$GITBOOK_DIR/versions/3.2.3"
   export PATH="$gitbook_lab/runtime/node_modules/.bin:$PATH"
   gitbook --version
   ```

   `GITBOOK_DIR` 是 GitBook CLI 自身支持的缓存位置；不替换编译器，不修改已安装插件。
   临时变量只对当前 shell 生效，不要求修改用户配置文件。

3. **执行完整构建验证**

   ```bash
   PYTHONDONTWRITEBYTECODE=1 python3 tests/language_build/validate.py \
     --work-dir "$gitbook_lab/fixtures"
   ```

   `--work-dir` 必须尚不存在。各样例保留源码、原生 `_book/`、最终 `_site/` 和构建日志。
   脚本会调用真实 `gitbook install`、`gitbook build`、现有目录摘要脚本和模板的路径后处理脚本。
   完成后写入 `report.json`，失败则返回非零退出码并指出日志路径。

   已安装模板插件时，可以添加 `--plugin-dir /绝对路径/node_modules` 复用依赖。
   此时生成样例的 `node_modules` 为链接；复制给其他电脑时应重新运行 `gitbook install`。

4. **在生成样例中独立编译**

   ```bash
   cd "$gitbook_lab/fixtures/added-language"
   gitbook install
   gitbook build
   make refine OUTPUT=_site-local
   ```

   或使用单个入口：

   ```bash
   make build OUTPUT=_site-next
   python3 -m http.server 8000 --bind 127.0.0.1 --directory _site-next
   ```

   浏览器访问 `http://127.0.0.1:8000/` 和 `http://127.0.0.1:8000/en/`。
   构建脚本已随样例复制，不依赖本测试目录或 Seenical 后端。

   - `gitbook build` 的原生 `_book/` 保留 GitBook 语言选择首页和语言目录。
   - `make build` 同时执行后处理，将默认语言发布到最终目录根路径。
   - 样例保留两份输出以便比较。仓库模板默认将最终产物写到 `.build/_book/`。
   - 默认最终目录为 `_site/`。显式指定输出目录时，脚本拒绝覆盖已有目录；重复构建请指定新的 `OUTPUT`，防止误删待比较产物。
   - 普通 `gitbook serve` 预览的是原生结构；最终公开路径应通过后处理产物预览。

5. **验证内容**

   - 原生单语言目录、双语言目录均能编译。
   - 中文首页、普通文章、嵌套目录首页、深层文章、中文文件名可访问。
   - 增加语言及旧结构转换后，所有旧公开文件路径继续存在。
   - 原始文章和附件复制前后字节一致；最终图片、附件字节一致。
   - HTML 链接、图片、脚本、CSS 资源、语言首页入口能解析到实际文件。
   - 原页面 canonical 不变，sitemap 中的站内地址有对应文件。
   - `make build` 再次构建得到相同公开文件集合，重新通过引用检查。
   - 隐藏附件、目录冲突、已有输出保护和路径重写由独立测试覆盖。

   样例语言入口通过 GitBook 原生 `_layouts` 扩展生成，仅验证地址，不是最终产品界面。

6. **HTTP 与单元测试**

   ```bash
   python3 tests/language_build/http_smoke.py "$gitbook_lab/fixtures"
   PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests/language_build -p 'test_*.py' -v
   PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_subdirectory_summary.py' -v
   ```

   HTTP 检查仅临时监听 `127.0.0.1` 的随机端口，结束后关闭；需要本地监听权限。
   它访问迁移前后文件地址、目录首页地址、中文编码地址和带查询参数的文章地址，输出 `http-report.json`。
   不连接真实托管站点，也不测试线上路由、CDN 或访问令牌。

7. **可选搜索诊断**

   现有生产模板关闭了原生 `search` 和 `lunr`。可额外启用它们复现多语言索引问题：

   ```bash
   PYTHONDONTWRITEBYTECODE=1 python3 tests/language_build/validate.py \
     --work-dir "$gitbook_lab/search-fixtures" --with-search
   ```

   诊断会对原生和后处理索引执行真实 lunr 查询，比较结果是否改变，并将已有插件的串语言问题写入
   `known_limitations`。此命令成功不表示搜索语言隔离通过，必须查看报告中的限制。
   本阶段不修复第三方搜索插件，也不默认启用这套搜索。

8. **原型边界**

   `site-layout.json` 描述语言目录和公开路径。本阶段只接受语言名目录、默认语言根路径、其他语言同名路径；
   不宣称已支持任意目录映射。后处理保留原生输出，对冲突报错。默认构建只替换由脚本生成的目录。

   真实旧站的定制插件、脚本动态生成的 URL、特殊主题、`srcset`、浏览器交互、非根路径完整部署、
   私有托管访问控制及线上 CDN 尚未验证。非根路径 URL 改写只有单元测试覆盖。
   正式迁移前仍需针对目标仓库建立路径清单、预览并检查部署方式；此报告不代替真实站点迁移验收。
