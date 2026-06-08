# Codex-Local 5 小时自主运行计划

> 目标：让 codex-local 从"能跑的 demo"变成"能用的产品"
> 执行者：codex-local 自主 agent
> 时间：5 小时
> 资源：DeepSeek API (sk-842a...)、RTX 4060、已有代码库

---

## 第 1 小时：跑全量 Eval，拿到真实基线

**目标：** 知道现在准确率到底是多少

**执行：**
```
1. 设置 DEEPSEEK_API_KEY=sk-842a3aa4bbcb482a89482585aa227171
2. 跑 python data/eval/run_eval.py --model deepseek-chat
3. 保存报告 data/eval/reports/eval-full-v1.json
4. 统计：总通过率、各类别通过率、各难度通过率
5. 列出所有失败任务 + 失败原因
```

**产出：**
- eval-full-v1.json（完整报告）
- 准确率数字（对比之前的 71%）
- 失败任务清单

**验收：** 50 个任务全部跑完，报告文件存在

---

## 第 2 小时：修复失败任务，提升准确率

**目标：** 把准确率从 71% 提升到 80%+

**执行：**
```
1. 读 eval 报告，按失败原因分类：
   - tool calling 失败（模型没调工具）
   - 逻辑错误（模型调了工具但改错了）
   - 超时（任务太复杂）
   - 上下文溢出（消息太长）

2. 对每类失败，针对性修复：
   - tool calling → 改 system prompt
   - 逻辑错误 → 加更多经验到 lessons.json
   - 超时 → 增加 max_iterations
   - 上下文溢出 → 改进消息裁剪

3. 修完后重跑失败任务，验证是否通过

4. git commit 所有修改
```

**产出：**
- 修复后的代码
- 改进后的 system prompt
- 新增的 lessons
- 第二轮 eval 报告

**验收：** 准确率 > 75%（至少提升 4%）

---

## 第 3 小时：收集训练数据，目标 500 条

**目标：** 够微调一个 7B 模型

**执行：**
```
1. 跑更多 eval 轮次（不同类别、不同难度）
2. 每次 LLM 调用自动保存到 data/training/
3. 过滤：只保留成功的 + 有工具调用的
4. 去重：按任务描述去重
5. 导出：转成 ChatML 格式
6. 统计：总条数、各类别分布、质量分布
```

**产出：**
- data/training/ 下 500+ 个 jsonl 文件
- data/finetune/chatml_final.jsonl（合并后的训练集）
- 数据统计报告

**验收：** 高质量训练数据 >= 500 条

---

## 第 4 小时：代码质量全面修复

**目标：** quality_guard 检查所有核心模块，修复 HIGH/CRITICAL 问题

**执行：**
```
1. 运行 quality_guard 检查所有核心文件：
   - runtime/loop.py
   - runtime/llm_client.py
   - runtime/decision_engine.py
   - runtime/session.py
   - tools/executor.py
   - skills/*.py

2. 按优先级修复：
   - CRITICAL（语法错误、eval/exec）→ 立刻修
   - HIGH（裸 except、高复杂度、shell=True）→ 必须修
   - MEDIUM（长函数、宽捕获）→ 尽量修
   - LOW（缺 docstring）→ 有空再修

3. 每修一个文件，跑 pytest 验证

4. 修完后跑全量测试：python -m pytest tests/ -q
```

**产出：**
- 修复后的代码
- quality_guard 报告（before/after 对比）
- 测试结果（必须全绿）

**验收：** CRITICAL = 0，HIGH <= 5，测试全绿

---

## 第 5 小时：生成报告 + 提交

**目标：** 记录所有成果，提交到 git

**执行：**
```
1. 汇总所有 eval 报告，生成对比表
2. 统计：
   - 准确率变化（71% → ?）
   - 训练数据量（0 → ?）
   - 代码质量变化（警告数 before/after）
   - 修复的问题数量
   - 新增的功能
3. 写最终报告：data/eval/autonomous_report.md
4. git commit 所有变更
5. git log --oneline 查看完整提交历史
```

**产出：**
- autonomous_report.md（完整报告）
- git 提交历史
- 准确率对比表
- 剩余问题清单

**验收：** 报告文件存在，git 干净

---

## 总时间分配

```
第 1 小时：跑 eval（~50 分钟）+ 分析结果（~10 分钟）
第 2 小时：修 bug + 改 prompt（~50 分钟）+ 验证（~10 分钟）
第 3 小时：收集数据（~40 分钟）+ 清洗导出（~20 分钟）
第 4 小时：质量检查（~20 分钟）+ 修复（~40 分钟）
第 5 小时：写报告（~30 分钟）+ 提交（~10 分钟）+ 复查（~20 分钟）
```

## 风险和应对

```
风险 1：DeepSeek API 额度用完
  应对：优先跑重要任务，跳过已通过的

风险 2：某些任务卡住（超时/死循环）
  应对：设 60 秒超时，跳过卡住的任务

风险 3：修代码引入新 bug
  应对：每修一个跑一次 pytest，发现问题立刻回滚

风险 4：训练数据质量差
  应对：只保留成功的 + 有工具调用的，过滤掉空响应
```

## 最终目标

```
5 小时后 codex-local 应该达到：
  - 准确率：75%+（从 71% 提升）
  - 训练数据：500+ 条（够微调）
  - 代码质量：CRITICAL = 0，HIGH <= 5
  - 测试：全绿
  - 文档：完整报告
  - Git：干净提交历史
```

---

**执行命令：**
```
启动：python skills/self_evolution_loop.py --cycles 5
监控：每小时检查 data/eval/reports/ 目录
结束：查看 data/eval/autonomous_report.md
```
