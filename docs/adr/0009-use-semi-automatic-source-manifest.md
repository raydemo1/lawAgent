# Use a Semi-Automatic Source Manifest Before Ingestion

LawAgent 第一阶段采用半自动采集流程：脚本负责发现、下载和解析候选材料，但必须先生成 `source_manifest` 供人工确认，确认后才进入清洗、语义增强、分块和入库。这个流程避免把误召回、失效法规或低相关材料直接写入知识库，也能体现真实 RAG 项目中的数据盘点和抽样审核。
