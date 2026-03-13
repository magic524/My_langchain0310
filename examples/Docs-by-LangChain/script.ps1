python .\contract_review_agent.py `
  --knowledge-dir "E:\Magic_wu\AI合同审查系统\train" `
  --input-file "E:\Magic_wu\AI合同审查系统\test\1-品牌球馆冠名合作协议\原合同：曲点品牌球馆冠名合作协议.docx" `
  --output "E:\Magic_wu\AI合同审查系统\test\1-品牌球馆冠名合作协议.review.md"


python examples/Docs-by-LangChain/ablation/v0/ablation_v0.py --input-file "E:\Magic_wu\AI合同审查系统\test\1-品牌球馆冠名合作协议\原合同：曲点品牌球馆冠名合作协议.docx" --output "E:\Magic_wu\AI合同审查系统\test\1-品牌球馆冠名合作协议.review_v0.md"
