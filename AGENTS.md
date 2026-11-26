# AI 协作规则

## 分支与合并

- 开始修改任何工程文件前，必须确认当前分支不是 `master`。如果当前位于 `master`，先创建并切换到独立工作分支，禁止直接更新 `master`。
- 所有代码、配置和文档改动都必须通过工作分支合并回 `master`，不得直接提交、推送或改写 `master`。
- 合并回 `master` 时必须保留合并提交，使用非 fast-forward 合并（`git merge --no-ff <工作分支>`），不得使用 fast-forward 合并。
- 需要同步 `master` 的最新改动时，应将 `master` 合并到工作分支，而不是反向直接更新 `master`。
