# CodeHacker

## 快速开始

只要求 Python 3.10+：

```bash
python -m codehacker.demo
```

接入真实 LLM：

```bash
python -m pip install -e ".[llm]"
cp .env.example .env
# 编辑 .env，填写真实的 key、base URL 和模型名
python -m codehacker.demo --use-llm
```

Windows PowerShell 可用 `Copy-Item .env.example .env` 代替 `cp`。配置示例：

```dotenv
LLM_API_KEY=replace-with-your-api-key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-5-mini
LLM_TIMEOUT_SECONDS=120
```

也兼容 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 和 `OPENAI_MODEL`。`.env` 已加入 `.gitignore`，程序日志只显示模型名和 Base URL，不会输出 Key。Key 会发送给配置的 Base URL，因此第三方 endpoint 应使用该服务自己的 Key，不要复用其他平台的凭据。Chat Completions 用法和自定义 `base_url` 均由[官方 OpenAI Python 客户端](https://github.com/openai/openai-python)支持。

关键输出如下：

```text
=== Phase I: evaluation-tool calibration ===
validator: 1 refinement(s)
  round 1: failures=[valid-minimum-rejected, n-overflow-accepted, missing-case-accepted], clean_streak=0
  round 2: failures=[none], clean_streak=1
  round 3: failures=[none], clean_streak=2
checker: 1 refinement(s)
  round 1: failures=[duplicate-output-accepted, non-semiprime-output-accepted, valid-reordered-output-rejected], clean_streak=0
  ...

=== Phase II: adversarial case generation ===
  [stress] input='1 31' verdict=AC
  [logic-guided] input='1 36' verdict=WA  <-- successful hack
  [logic-guided] input='1 40' verdict=WA  <-- successful hack
  [logic-guided] input='1 44' verdict=WA  <-- successful hack

summary: 3 successful hack(s) from 6 candidate(s)
```

运行测试：

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

## Demo 在做什么

示例采用论文 Appendix K 的 Codeforces 1388A 案例。错误提交固定输出：

```cpp
cout << "6 10 14 " << n - 30 << "\n";
```

题目要求四个正整数互不相同。当 `n - 30` 分别等于固定项 `6`、`10`、`14` 时，得到：

| 输入 `n` | 错误输出 | 失败原因 |
| ---: | --- | --- |
| 36 | `6 10 14 6` | `6` 重复 |
| 40 | `6 10 14 10` | `10` 重复 |
| 44 | `6 10 14 14` | `14` 重复 |

Phase I 先修复一个故意有缺陷的 Validator 和 Checker；Phase II 的 Analyst 再从固定构造中推导 `n - 30 ∈ {6, 10, 14}`，由 logic-guided generator 生成三个合法反例。Stress generator 同时覆盖最小值、可行性边界和最大值；Anti-hash 模块检测到目标不使用哈希后保持空闲。

## 代码结构

```text
codehacker/
├── core.py        # 通用 Phase I 校准循环、Judge 与 Phase II 调度
├── demo.py        # 1388A 的 Validator/Checker/Analyst/Generators
├── llm.py         # Key/Base URL 配置和 OpenAI-compatible 客户端
└── __init__.py
.env.example       # 不含秘密的环境变量模板
tests/
└── test_demo.py   # 校准、hack、非法输入过滤和 LLM 配置测试
```

论文概念和代码入口的对应关系：

| 论文组件 | 本仓库实现 |
| --- | --- |
| Validator Refinement (Algorithm 1) | `calibrate_validator` + `ValidatorAgent` |
| Checker Refinement (Algorithm 2) | `calibrate_checker` + `CheckerAgent` |
| Code Analyst | `CaptainFlintAnalyst` / `LLMCaptainFlintAnalyst` |
| Stress / LLM-based / Anti-hash | `StressGenerator` / `LogicGuidedGenerator` / `AntiHashGenerator` |
| 三项 hack 判定条件 | `Judge.evaluate` |
| Phase II 迭代 | `run_phase_two` |

## 扩展到完整 Agent 和沙箱

`--use-llm` 已经会通过配置的 endpoint 调用真实模型完成 Code Analyst 阶段。核心层只依赖 Python Protocol，要把模型进一步接入 Phase I 和其他 Phase II 模块，可替换 demo 中的确定性组件：

1. 实现 `ValidatorAgent` 和 `CheckerAgent`，在 `initial/attack/refine` 中调用模型；
2. 对 Checker 的 `y_true` 使用标准解或独立 judge 交叉验证后再反馈，避免把幻觉写入评测工具；
3. 实现新的 `CaseGenerator.generate(plan)`，让模型输出输入生成器源码而非超长原始输入；
4. 将 `Judge` 的函数式 `Submission` 替换为带编译、超时、内存限制和进程隔离的执行后端；
5. 对 rolling hash 目标补充 LLL/SVP 或 birthday-attack generator。

`Judge` 会先过滤非法输入，并要求 reference solution 的输出通过 Checker；因此无效 case 或损坏的评测基础设施不会被误记为 successful hack。当前轻量执行器会识别 AC、WA 和 Python 异常对应的 RE；TLE/MLE 枚举已预留，需由真实沙箱后端返回。



## 引用

```bibtex
@inproceedings{shi-etal-2026-codehacker,
  title     = {CodeHacker: Automated Test Case Generation for Detecting Vulnerabilities in Competitive Programming Solutions},
  author    = {Shi, Jingwei and Yin, Xinxiang and Huang, Jing and Tao, Shengyu and Zhao, Jinman},
  booktitle = {Proceedings of the 64th Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers)},
  year      = {2026},
  pages     = {2352--2382},
  url       = {https://aclanthology.org/2026.acl-long.108/}
}
```
