# Self Evolve Project

多文件版自我进化主控系统。

核心循环：

    执行任务 -> 评估结果 -> 分析失败 -> 改进 Prompt -> 再执行 -> 对比分数 -> 晋级或丢弃

## 初始化

    python run.py init

## 跑一轮 demo

    python run.py cycle --config configs/default.json

## 跑多轮

    python run.py loop --config configs/default.json --cycles 3
