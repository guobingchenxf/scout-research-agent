# 人工校准盲标表

> 判断每条 answer 是否通过。**不要参考 rule grader 结果**；本文件也刻意
> 不含 rule/judge verdict。判定标准见下，完成后把 pass/fail 填到
> `eval/calibration_labels.csv`。

判定为 pass 需同时满足：

1. answer 覆盖 gold answer 的关键事实（语义一致即可，不要求措辞相同）；
2. required citations 都存在，且引用内容能支撑对应 claim；
3. 没有与 gold answer 冲突或 forbidden claims 中的断言；
4. abstention 题明确说明“语料中没有足够证据”，且没有编造引用；
5. conflict 题明确暴露来源分歧，而不是静默取一方或平均。

任意一条不满足即 fail。只判断 answer，不判断 UI、延迟或成本。

## 1. `fact_trtllm_kernels` — fact（difficulty 1）

**Question:** TensorRT-LLM 如何优化 LLM inference？

**Gold answer:**

> TensorRT-LLM 用 specialized kernels、高效 runtime 和 Pythonic framework 优化 LLM inference。

**Required citations:** docs:github:NVIDIA/TensorRT-LLM

**Gold evidence:**

- `docs:github:NVIDIA/TensorRT-LLM` (README): TensorRT LLM optimizes inference for LLMs and Visual Gen models with specialized kernels

**Model answer:**

> # TensorRT-LLM README
>
> Source: https://github.com/NVIDIA/TensorRT-LLM
>
> <div align="center">
>
> TensorRT LLM
> ===========================
> <h4>TensorRT LLM optimizes inference for LLMs and Visual Gen models with specialized kernels for common operations, an efficient runtime, and a pythonic framework that enables you to customize and extend the system.</h4>
>
> [![Documentation](https://img.shields.io/bad

**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`

## 2. `fact_tamarin_tiers` — fact（difficulty 1）

**Question:** Tamarin 的压缩结构是什么？

**Gold answer:**

> Tamarin 使用三层可逆压缩：4-bit focal tier、3-bit group summary tier、CPU-RAM archive。

**Required citations:** crossref:10.21203/rs.3.rs-10297225/v1

**Gold evidence:**

- `crossref:10.21203/rs.3.rs-10297225/v1` (abstract): a three-tier reversible compression scheme

**Model answer:**

> INSUFFICIENT_EVIDENCE — 无法确定 Tamarin 的压缩结构细节。可核实的仅有：Tamarin (HSQ) 是一篇题为《Tamarin (HSQ): Reversible Hierarchical KV-Cache Compression for LLM Inference》的工作（DOI 10.21203/rs.3.rs-10297225/v1），属于面向 LLM 推理的可逆、分层式 KV-cache 压缩，其动机是长上下文下 KV cache 成为 GPU 显存的主要占用者（例如 32K tokens 时 Qwen3-8B 的 fp16 KV cache 约 4.5 GiB）。但关于“压缩结构”本身（层级划分、focal/summary/archive 之类的具体构件、位平面或重建机制）在已获证据中没有逐字出现，因此不做推测。

**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`

## 3. `fact_secrag_dimensions` — fact（difficulty 1）

**Question:** Secure-RAG 评估哪些维度？

**Gold answer:**

> Secure-RAG 评估 factual accuracy、hallucination avoidance、adversarial robustness、bias/fairness、toxicity、security 和 calibration。

**Required citations:** crossref:10.20944/preprints202510.0418.v1

**Gold evidence:**

- `crossref:10.20944/preprints202510.0418.v1` (abstract): factual accuracy, hallucination avoidance, adversarial robustness, bias and fairness, toxicity, security, and calibration

**Model answer:**

> Secure-RAG 从多个维度评估 RAG 系统，摘要明确列出的维度包括：事实准确性（factual accuracy）、幻觉规避（hallucination avoidance）、对抗鲁棒性（adversarial robustness）、偏见与公平性（bias and fairness）、毒性（toxicity）、安全性（security）以及校准（calibration）。其定位是模块化、安全优先的多维评估套件，并在查询、检索、生成各阶段设置轻量监控器来计算标准化指标。

**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`

## 4. `hop_vllm_vs_sglang` — multi_hop（difficulty 2）

**Question:** vLLM 和 SGLang 在 KV cache/prefix 管理上的核心差异是什么？

**Gold answer:**

> vLLM 用 PagedAttention 管理 attention key/value memory；SGLang 用 RadixAttention 做 exact token-level prefix caching。

**Required citations:** docs:github:vllm-project/vllm, crossref:10.2139/ssrn.7290195

**Gold evidence:**

- `docs:github:vllm-project/vllm` (README): Efficient management of attention key and value memory
- `crossref:10.2139/ssrn.7290195` (abstract): exact token-level prefix caching (SGLang RadixAttention)

**Model answer:**

> # JaccardServe: Cross-Request Prefill Acceleration in LLM Serving via MinHash-LSH Token Shingling
>
> Source: https://doi.org/10.2139/ssrn.7290195
>
> ## Abstract
>
> Reusing computed key-value (KV) caches across requests is a highly effective optimization in serving large language models (LLMs), but the field has split into three main approaches: exact block-level prefix caching (vLLM APC), exact token-le # JaccardServe: Cross-Request Prefill Acceleration in LLM Serving via MinHash-LSH Token Shingling
>
> Source: https://doi.org/10.2139/ssrn.6851358
>
> ## Abstract
>
> Cross-request reuse of computed key-value (KV) cache is one of the most effective optimizations in production large language model (LLM) serving, but the field has fragmented into three operating points: exact block-level prefix caching (vLLM vLLM
>  
>  
>  
>  
>  
>  Home
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  Initializing search
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  GitHub
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  Home
>
>  
>  
>  
>
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  User Guide
>
>  
>  
>  
>  
>
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  Dev

**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`

## 5. `hop_keepkv_vs_tamarin` — multi_hop（difficulty 2）

**Question:** KeepKV 和 Tamarin 对 KV cache 压缩的取舍有什么不同？

**Gold answer:**

> KeepKV 用 adaptive merging 保留更多信息；Tamarin 用三层可逆压缩，避免 eviction/merge 永久丢失未来才相关的信息。

**Required citations:** crossref:10.1609/aaai.v40i39.40611, crossref:10.21203/rs.3.rs-10297225/v1

**Gold evidence:**

- `crossref:10.1609/aaai.v40i39.40611` (abstract): a novel adaptive KV cache merging method designed to preserve performance under strict memory constraints
- `crossref:10.21203/rs.3.rs-10297225/v1` (abstract): a three-tier reversible compression scheme

**Model answer:**

> # KeepKV: Achieving Periodic Lossless KV Cache Compression for Efficient LLM Inference
>
> Source: https://doi.org/10.1609/aaai.v40i39.40611
>
> ## Abstract
>
> Efficient inference of large language models (LLMs) is hindered by an ever-growing key-value (KV) cache, making KV cache compression a critical research direction. Traditional methods selectively evict less important KV cache entries, which leads t # Tamarin (HSQ): Reversible Hierarchical KV-Cache Compression for LLM Inference
>
> Source: https://doi.org/10.21203/rs.3.rs-10297225/v1
>
> ## Abstract
>
> Abstract The key–value (KV) cache is the dominant GPU-memory consumer in long-context LLM inference. At 32K tokens, a Qwen3-8B model holds roughly 4.5 GiB of fp16 KV cache against about 5 GiB of int4 weights, and the cache grows linearly with context.  A Survey of LLM KV Cache Management Strategies and the SR-KV Framework
>
> Source: https://doi.org/10.26438/ijcse.v14i9.7546
>
> ## Abstract
>
> Large Language Models (LLMs) rely on a Key-Value (KV) Cache to avoid recomputation of attention information for the previously generated tokens, but the cache keeps growing linearly with the sequence length and thus quickly becomes the dominant memory bottleneck d

**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`

## 6. `hop_query_decomp_rerank` — multi_hop（difficulty 2）

**Question:** 多跳 RAG 中 query decomposition 和 cross-encoder reranking 分别解决什么问题？

**Gold answer:**

> query decomposition 把复杂问题拆成 self-contained sub-questions；cross-encoder reranking 在每一步重排候选，缓解 dense retrieval 的 semantic drift。

**Required citations:** crossref:10.66245/jyi.v1.i1.002

**Gold evidence:**

- `crossref:10.66245/jyi.v1.i1.002` (abstract): decomposes complex queries into self-contained sub-questions and employs a Cross-Encoder to rerank candidates

**Model answer:**

> # The Impact of Query Decomposition and Cross-Encoder Reranking in Multi-Hop Retrieval-Augmented Generation
>
> Source: https://doi.org/10.66245/jyi.v1.i1.002
>
> ## Abstract
>
> Retrieval-Augmented Generation (RAG) has emerged as a promising paradigm for open-domain question answering. However, standard single-hop retrieval often fails on complex, multi-hop queries where the answer requires synthesizing i # Candidate Evidence Reranking and Risk-Aware Answer Selection in Multi-Hop Retrieval-Augmented Generation
>
> Source: https://doi.org/10.21203/rs.3.rs-11009751/v1
>
> ## Abstract
>
> Abstract Multi-hop retrieval-augmented generation (RAG) can fail to fully exploit useful evidence even after it has entered the candidate pool, because ranking and limited context budgets determine which documents are actuall # Optimizing Information Retrieval in RAG through Intelligent Reranking and Follow-Up Query Predictions
>
> Source: https://doi.org/10.21203/rs.3.rs-7506627/v1
>
> ## Abstract
>
> Abstract Reranking is a crucial process in Retrieval-Augmented Generation (RAG) systems as it significantly impacts the quality and the relevance of retrieved knowledge chunks. Conventional reranking models usually prioritize sem

**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`

## 7. `hop_rerank_followup` — multi_hop（difficulty 2）

**Question:** RAG reranking 如何利用 follow-up query prediction？

**Gold answer:**

> 把 LLM 预测的 follow-up queries 和初始 query 结合，用 fine-tuned weighting 重新排序，更好捕捉演化中的用户意图。

**Required citations:** crossref:10.21203/rs.3.rs-7506627/v1

**Gold evidence:**

- `crossref:10.21203/rs.3.rs-7506627/v1` (abstract): incorporating LLM-generated predicted follow-up queries coupled with the initial user query

**Model answer:**

> 根据目前可获得的证据，只能给出高层结论：该工作把 follow-up query prediction 视为“用户意图预测”信号，并将其整合进 RAG 的重排过程，采用 embedding-driven、adaptive reranking 来优化检索与生成流程。
>
> 但证据不足以回答具体“如何”利用，例如：预测出的 follow-up queries 是否与原始 query 拼接、是否用加权分数融合、reranker 的训练目标是什么、在哪些数据集上带来多少提升。这些机制细节未在当前证据中逐字出现，因此不能臆测。

**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`

## 8. `hop_harness_taxonomy` — multi_hop（difficulty 2）

**Question:** LLM 评测 harness 分为哪几类？

**Gold answer:**

> 分为 benchmark harness、agent harness 和 tool-use harness 三类。

**Required citations:** crossref:10.20944/preprints202609.0236.v1

**Gold evidence:**

- `crossref:10.20944/preprints202609.0236.v1` (abstract): We distinguish three harness families.

**Model answer:**

> 根据检索到的分类学预印本，LLM 评测 harness 分为三类：1）Benchmark harness（基准评测 harness）；2）Agent harness（智能体评测 harness）；3）Tool-Use harness（工具使用评测 harness）。不过，当前证据只支持标题层面的分类枚举，尚不足以给出三类的严格定义、评分契约、环境要求及相互边界；需要该文献全文才能进一步确认。

**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`

## 9. `hop_scheduler_portability` — multi_hop（difficulty 2）

**Question:** LLM-serving scheduler 排名在不同 workload 上可移植吗？

**Gold answer:**

> 部分可移植：两个 source 的跨源排名一致性可到 Kendall tau 1.0，但涉及 BurstGPT 时可低至 0.55。

**Required citations:** crossref:10.21203/rs.3.rs-10935389/v1

**Gold evidence:**

- `crossref:10.21203/rs.3.rs-10935389/v1` (abstract): Cross-source rank agreement is strong between two sources (Kendall’s τ b up to 1.0)
- `crossref:10.21203/rs.3.rs-10935389/v1` (abstract): as low as 0.55

**Model answer:**

> # How Portable Are LLM-Serving Scheduler Rankings Across Workloads, Operating Regions, and Metrics? Source: https://doi.org/10.21203/rs.3.rs-10935389/v1
>
> ## Abstract
>
> Abstract Large language model (LLM) serving systems are typically compared on one workload, operating region, and metric. We present the LLM-Serving Scheduler Portability Benchmark (LSSP), a preregistered evaluation of scheduling pol # Module Counterfactuals for Attributing LLM Serving Scheduler Effects
>
> Source: https://doi.org/10.21203/rs.3.rs-11569472/v1
>
> ## Abstract
>
> Abstract An unchanged aggregate score can hide a scheduler component’s effects. We specify module interventions for large language model serving that pair complete runs on matched workloads and compare recommendations at identical simulated states. Beyond which # StepCache: Step-Level Reuse with Lightweight Verification and Selective Patching for LLM Serving
>
> Source: https://doi.org/10.21203/rs.3.rs-9077245/v1
>
> ## Abstract
>
> Abstract We address LLM serving workloads where repeated requests share a common solution structure but differ in localized constraints such as output schema, variable names, or numeric constants. Prior caching approaches typically re

**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`

## 10. `cmp_vllm_trtllm` — comparison（difficulty 2）

**Question:** vLLM 和 TensorRT-LLM 的定位差异？

**Gold answer:**

> vLLM 强调 easy、fast、cheap 的 LLM serving；TensorRT-LLM 用 specialized kernels 和 efficient runtime 优化 LLM/Visual Gen inference。

**Required citations:** docs:github:vllm-project/vllm, docs:github:NVIDIA/TensorRT-LLM

**Gold evidence:**

- `docs:github:vllm-project/vllm` (README): Easy, fast, and cheap LLM serving for everyone
- `docs:github:NVIDIA/TensorRT-LLM` (README): TensorRT LLM optimizes inference for LLMs and Visual Gen models with specialized kernels

**Model answer:**

> # vLLM README
>
> Source: https://github.com/vllm-project/vllm
>
> <!-- markdownlint-disable MD001 MD041 -->
> <p align="center">
>   <picture>
>     <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/vllm-project/vllm/main/docs/assets/logos/vllm-logo-text-dark.png">
>     <img alt="vLLM" src="https://raw.githubusercontent.com/vllm-project/vllm/main/docs/assets/logos/vllm-log # TensorRT-LLM README
>
> Source: https://github.com/NVIDIA/TensorRT-LLM
>
> <div align="center">
>
> TensorRT LLM
> ===========================
> <h4>TensorRT LLM optimizes inference for LLMs and Visual Gen models with specialized kernels for common operations, an efficient runtime, and a pythonic framework that enables you to customize and extend the system.</h4>
>
> [![Documentation](https://img.shields.io/bad # vLLM documentation
>
> Source: https://docs.vllm.ai/en/latest/
>
> vLLM 
>  
>  
>  
>  
>  
>  
>  
>  
>  
>
>
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  Skip to content
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  You are viewing the latest developer preview docs. Click here to view docs for the latest stable release. vLLM
>  
>  
>  
>  
>  
>  Home
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  
>  

**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`

## 11. `cmp_keepkv_eviction` — comparison（difficulty 2）

**Question:** KeepKV 相比传统 KV cache eviction 的优势？

**Gold answer:**

> 传统 eviction 丢弃不重要的 KV entries，造成信息损失和 hallucination；KeepKV 用 merging 保留更多信息，并减少 attention 分布不一致。

**Required citations:** crossref:10.1609/aaai.v40i39.40611

**Gold evidence:**

- `crossref:10.1609/aaai.v40i39.40611` (abstract): Traditional methods selectively evict less important KV cache entries, which leads to information loss and hallucinations.

**Model answer:**

> # KeepKV: Achieving Periodic Lossless KV Cache Compression for Efficient LLM Inference
>
> Source: https://doi.org/10.1609/aaai.v40i39.40611
>
> ## Abstract
>
> Efficient inference of large language models (LLMs) is hindered by an ever-growing key-value (KV) cache, making KV cache compression a critical research direction. Traditional methods selectively evict less important KV cache entries, which leads t This paper presents a survey of training free strategies proposed to manage this bottleneck, organising them into four families: hard token eviction, cache merging and semantic compression, low rank reduction and quantization, and adaptive budget allocation across layers and heads. Across the reviewed literature, eviction based methods bound memory efficiently but discard context irreversibly, whi # EMPIRIC: Exploring Missing Pieces in KV Cache Compression for Reducing Computation, Storage, and Latency in Long-Context LLM Inference
>
> Source: https://doi.org/10.1145/3759441.3759448
>
> ## Abstract
>
> Transformer-based Large Language Models (LLMs) heavily depend on the KV cache for efficient handling of long context sequences. However, the size of the KV cache grows linearly with the input sequence # Tokenskipping : a practical and robust KV cache pruning method for long-context llm inference
>
> Source: https://doi.org/10.58837/chula.the.2025.849
>
> ## Abstract
>
> Large Language Models (LLMs) have demonstrated remarkable capabilities, yet their deployment in long-context scenarios is severely hampered by the extensive memory and computational costs associated with the Key-Value (KV) cache. This pa

**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`

## 12. `cmp_candidate_rerank` — comparison（difficulty 2）

**Question:** 候选证据 reranking 和按答案频率选择有什么不同？

**Gold answer:**

> 候选证据 reranking 结合 trajectory ranks、lexical matching 和 event-entity 结构特征；答案频率不一定等于 correction value。

**Required citations:** crossref:10.21203/rs.3.rs-11009751/v1

**Gold evidence:**

- `crossref:10.21203/rs.3.rs-11009751/v1` (abstract): candidate evidence reranking (CAPE) combines trajectory ranks, lexical matching, and event-entity structural features

**Model answer:**

> # Candidate Evidence Reranking and Risk-Aware Answer Selection in Multi-Hop Retrieval-Augmented Generation
>
> Source: https://doi.org/10.21203/rs.3.rs-11009751/v1
>
> ## Abstract
>
> Abstract Multi-hop retrieval-augmented generation (RAG) can fail to fully exploit useful evidence even after it has entered the candidate pool, because ranking and limited context budgets determine which documents are actuall # Choosing Evidence Before Answering: Single-Retrieval Decisions RAG versus Embedding-Only RAG
>
> Source: https://doi.org/10.2139/ssrn.7627701
>
> ## Abstract
>
> Embedding similarity identifies passages related to a question, but topical similarity does not establish answer support. We evaluate a fixed single-retrieval policy that scores embedding candidates against an explicit four-level support rubric  # Consistency-Aware Reranking via Preference Graph Repair: Structural Gains and Conditional Retrieval Effects
>
> Source: https://doi.org/10.21203/rs.3.rs-9335700/v1
>
> ## Abstract
>
> Abstract Preference-based reranking provides a flexible way to combine ranking signals, but the induced preference graph may contain directed cycles that prevent a fully consistent ordering. This paper studies consistency-a

**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`

## 13. `cmp_governance_auth` — comparison（difficulty 2）

**Question:** 独立 authorization layer 是否显著降低 healthcare agent 的 unsafe actions？

**Gold answer:**

> 没有显著降低：fully governed 0.7% vs unconstrained 0.4%，差异 +0.4 points，95% CI 跨 0，P=0.6875。

**Required citations:** crossref:10.21203/rs.3.rs-11133816/v1

**Gold evidence:**

- `crossref:10.21203/rs.3.rs-11133816/v1` (abstract): Unsafe actions occurred in 0.7% of fully governed versus 0.4% of unconstrained episodes

**Model answer:**

> INSUFFICIENT_EVIDENCE — 现有证据不足以判断独立 authorization layer 是否显著降低 healthcare agent 的 unsafe actions。检索到的唯一相关来源（crossref:10.21203/rs.3.rs-11133816/v1）标题为《A live agent benchmark of independent action authorization for healthcare AI agents》，说明该基准确实针对此问题，但可获取的仅是其摘要开头（“Benchmarks measure what healthcare AI agents can do, not what they may be aut…”），其中不含任何 unsafe action 比率、基线对比、降幅数字或统计显著性结论。另一条被读取的来源 github:superlinked/sie 是一个开源推理服务器仓库，与 healthcare agent 的 authorization 效果无关，不构成证据。因此对该问题既不能肯定也不能否定，需要获取该论文的结果/发现部分全文后才能作答。

**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`

## 14. `proc_tamarin` — procedure（difficulty 2）

**Question:** Tamarin 的三层压缩分别是什么？

**Gold answer:**

> L1 是非摘要的 4-bit focal tier；L2 是 3-bit learned group-summary vectors；L3 是 CPU-RAM archive，保存 4-bit compressed originals。

**Required citations:** crossref:10.21203/rs.3.rs-10297225/v1

**Gold evidence:**

- `crossref:10.21203/rs.3.rs-10297225/v1` (abstract): a non-summarized 4-bit focal tier (L1), a 3-bit tier of learned group-summary vectors (L2), and a CPU-RAM archive of all compressed originals stored at 4-bit precision (L3)

**Model answer:**

> 证据只能确认 Tamarin（HSQ）是一种面向 LLM 推理的“可逆分层 KV-cache 压缩”方法；但所提供的摘要并未列出或命名具体的三个压缩层级，因此无法从现有证据中给出这三层分别是什么。摘要仅说明其设计是分层的、可逆的，并将自身与两类已有做法区分开来：逐条量化（安全但有上限）以及永久驱逐/合并 token（可能破坏信息，这些信息只有在未来查询已知后才变得相关）。要回答“三层分别是什么”，需要 Tamarin 论文的正文（方法部分），而该部分不在本证据集中。

**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`

## 15. `proc_secrag` — procedure（difficulty 2）

**Question:** Secure-RAG 的评估流程是什么？

**Gold answer:**

> 对 query、retrieval、generation 每个阶段加 lightweight monitors，做多维评估。

**Required citations:** crossref:10.20944/preprints202510.0418.v1

**Gold evidence:**

- `crossref:10.20944/preprints202510.0418.v1` (abstract): instruments each stage (query, retrieval, generation) with lightweight monitors

**Model answer:**

> Secure-RAG 的评估流程可归纳为以下几个有序步骤（依据论文摘要描述）：
>
> 1. 确立多维评估框架：将评估设计为一个模块化、安全优先（security-first）的评估套件，用于对 RAG 系统进行多维度评测，覆盖事实准确性（factual accuracy）、幻觉规避（hallucination avoidance）、对抗鲁棒性（adversarial robustness）、偏见与公平性（bias and fairness）、毒性（toxicity）、安全性（security）以及校准（calibration）等维度 [e1][e2]。
>
> 2. 在查询阶段（query）布置监控器：对 RAG 流水线的查询阶段进行插桩（instrument），部署轻量级监控器以采集该阶段的信号 [e1][e2]。
>
> 3. 在检索阶段（retrieval）布置监控器：同样对检索阶段进行插桩，部署轻量级监控器 [e1][e2]。
>
> 4. 在生成阶段（generation）布置监控器：对生成阶段进行插桩，部署轻量级监控器 [e1][e2]。
>
> 5. 计算标准化指标：由这些轻量级监控器计算标准化指标（standardized metrics），从而在各阶段和上述各维度上形成可比较的量化评测结果 [e1][e2]。
>
> 6. 进行示例性评估并检验可靠性—效用权衡：通过一次示例性评估（illustrative evaluation）验证 Secure-RAG 能在不牺牲效用（utility）的前提下提升可靠性（reliability）[e1][e2]。
>
> 注意：现有证据仅来自论文摘要，未给出各指标的具体定义、评分聚合方式或阈值，因此上述流程为框架层面的顺序，而非完整的操作细节。

**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`

## 16. `conf_scheduler_repro` — conflict（difficulty 3）

**Question:** Serving benchmark 的排名是否既可移植又可复现？

**Gold answer:**

> 存在张力：scheduler 排名跨源可高度一致（Kendall tau 到 1.0），但 LLM-based measurement 的复现性依赖 serving stack。

**Required citations:** crossref:10.21203/rs.3.rs-10935389/v1, crossref:10.2139/ssrn.7083993

**Gold evidence:**

- `crossref:10.21203/rs.3.rs-10935389/v1` (abstract): Cross-source rank agreement is strong between two sources (Kendall’s τ b up to 1.0)
- `crossref:10.2139/ssrn.7083993` (abstract): reproducibility depends on the serving stack

**Model answer:**

> 不能简单认为 Serving benchmark 的排名既完全可移植又可复现。直接证据显示：LSSP 的跨工作负载来源排名一致性在两个来源之间很强（Kendall’s τ_b 最高可达 1.0），但涉及第三个来源 BurstGPT 时最低降至 0.55，且 3.6% 的成对比较出现有统计支持的反转；跨评估指标的排名可移植性更有限（中位 τ_b=0.419，top-policy 一致率 31.9%）。因此排名可移植性是部分的、依赖来源和指标。可复现性方面，LSSP 是预注册研究且每个配置执行两次，但提供的证据未报告重复运行之间的排名一致性；另一来源则强调可复现的 LLM 测量取决于 serving stack，不能仅靠强制最可能答案来保证。故基于现有证据，不能同时充分支持“既可移植又可复现”。

**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`

## 17. `conf_context_strategy` — conflict（difficulty 3）

**Question:** 在 forced context compression 下，哪种 context-management 策略最好？

**Gold answer:**

> 没有单一最优；drop oldest、LLM summary、retrieve relevant turns 各有取舍，需要在受控 fact-recall 任务上比较。

**Required citations:** crossref:10.2139/ssrn.6961019

**Gold evidence:**

- `crossref:10.2139/ssrn.6961019` (abstract): dropping the oldest turns, or replacing them with an LLM-generated summary
- `crossref:10.2139/ssrn.6961019` (abstract): under a controlled, fact-recall task

**Model answer:**

> 现有证据只能确认存在一项针对该问题的受控实证评估，但检索到的内容仅为论文摘要，未报告任何实验结果，因此无法判定在 forced context compression 下哪种 context-management 策略最好。摘要指出，该研究在受控的事实回忆（fact-recall）任务上正面比较了三种策略：(1) 丢弃最旧的对话轮次（dropping the oldest turns），(2) 用 LLM 生成的摘要替换旧轮次，(3) 不论时间远近、只检索与当前查询最相关的轮次。摘要称第三种策略在检索增强系统中常见，但很少与前两种在受控条件下做正面比较；这属于研究动机与实验设计，而非性能结论，故无法据此排序优劣。

**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`

## 18. `abs_sglang_acquisition` — abstention（difficulty 2）

**Question:** SGLang 在 2026 年被哪家公司收购？

**Gold answer:**

> INSUFFICIENT_EVIDENCE

**Model answer:**

> INSUFFICIENT_EVIDENCE

**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`

## 19. `abs_h200_memory` — abstention（difficulty 2）

**Question:** NVIDIA H200 的显存容量是多少？

**Gold answer:**

> INSUFFICIENT_EVIDENCE

**Model answer:**

> INSUFFICIENT_EVIDENCE

**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`

## 20. `abs_nobel` — abstention（difficulty 2）

**Question:** 2026 年诺贝尔物理学奖得主是谁？

**Gold answer:**

> INSUFFICIENT_EVIDENCE

**Model answer:**

> INSUFFICIENT_EVIDENCE

**Human verdict:** 填 `pass` 或 `fail` → `eval/calibration_labels.csv`
