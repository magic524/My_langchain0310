#!/bin/bash

#######      chmod +x script.sh
#######      ./script.sh

/home/magic524/miniconda3/envs/langchain/bin/python contract_review_agent.py \
  --knowledge-dir "/mnt/e/Work/AI合同审查系统0310/合同数据-2026.3.6/train合同" \
  --input-file "/mnt/e/Work/AI合同审查系统0310/合同数据-2026.3.6/test合同/1-品牌球馆冠名合作协议/原合同：曲点品牌球馆冠名合作协议.docx"
