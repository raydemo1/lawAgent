# Use Structure-Aware Chunking Without Summary Prefixes

LawAgent 第一版按文档类型采用结构化分块：法律法规优先按章、节、条切分，政策问答按问答和小标题切分，隐私政策按 section heading 切分。文档摘要作为独立字段参与检索和展示，不直接拼进 chunk 正文，避免摘要语义过强导致真正包含答案的正文 chunk 在 Top-K 中被挤出。
