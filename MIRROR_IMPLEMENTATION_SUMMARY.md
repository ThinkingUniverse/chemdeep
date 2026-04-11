# Scholar 镜像导航配置说明

本次实现已经从“单个镜像列表”调整为“镜像导航地址集合 + 可选直连镜像补充”。

## 核心变化

- `CHEMDEEP_LANFANSHU_MIRROR_NAV_URLS`
  - 含义：镜像导航页集合。
  - 用途：系统先访问这些导航页，再从页面中提取 scholar / xueshu / 谷歌学术镜像链接。
  - 示例：`https://ac.scmor.com/;https://your-nav.example.com/`
- `CHEMDEEP_LANFANSHU_MIRROR_URLS`
  - 含义：可选的直连镜像补充列表。
  - 用途：当导航页失效、解析不到镜像，或者需要手工追加私有镜像时作为补充与兜底。
  - 示例：`https://scholar.lanfanshu.cn,https://sc.panda985.com`

## 配置位置

### 1. ChemDeep 主项目 `.env`

文件：`config/.env`

已加入：

```env
CHEMDEEP_LANFANSHU_MIRROR_NAV_URLS=https://ac.scmor.com/
CHEMDEEP_LANFANSHU_MIRROR_URLS=
```

### 2. Node MCP 专用 env

文件：`config/paper-search-mcp-nodejs.env`

已加入同名配置：

```env
CHEMDEEP_LANFANSHU_MIRROR_NAV_URLS=https://ac.scmor.com/
CHEMDEEP_LANFANSHU_MIRROR_URLS=
```

### 3. MCP 启动时的 env 覆盖

在 Cherry Studio / OpenClaw 的 MCP 配置中，也可以显式传入这两个变量进行覆盖。

## MCP 读取逻辑

Node MCP 启动文件 `paper-search-mcp-nodejs/src/server.ts` 已调整为：

1. 先加载共享配置 `config/.env`
2. 再加载 MCP 专用配置 `config/paper-search-mcp-nodejs.env`
3. MCP 专用配置可覆盖共享配置

这样可以满足两个目标：

- ChemDeep 主项目统一在 `.env` 中维护镜像导航配置
- MCP 仍然保留自己的独立覆盖能力

## 运行时策略

`MirrorManager` 现在会按以下顺序构建镜像池：

1. `CHEMDEEP_LANFANSHU_MIRROR_URLS` 中的直连镜像
2. 内置默认镜像
3. 从 `CHEMDEEP_LANFANSHU_MIRROR_NAV_URLS` 导航页中动态解析出来的镜像

搜索时的回退顺序：

1. 优先尝试当前可用镜像
2. 某镜像失败后自动尝试下一个
3. 所有镜像都失败后回退到 `https://xueshu.lanfanshu.cn`

## 相关文件

- `config/.env`
- `config/paper-search-mcp-nodejs.env`
- `config/settings.py`
- `core/mirror_manager.py`
- `core/scholar_search.py`
- `paper-search-mcp-nodejs/src/server.ts`
- `paper-search-mcp-nodejs/src/platforms/MirrorManager.ts`
- `paper-search-mcp-nodejs/src/platforms/LanfanshuSearcher.ts`
- `mcp_server/README.md`
- `mcp_server/SETUP.md`
- `test_mirror_search.py`

## 已验证内容

- Python `MirrorManager` 可从 `config/.env` 读取 `CHEMDEEP_LANFANSHU_MIRROR_NAV_URLS`
- Node MCP 项目 `npm run build` 通过
- MCP 文档与配置示例已加入镜像导航变量说明
