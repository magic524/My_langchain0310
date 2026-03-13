conda activate langchain; python Contract_Review_System\v1\scripts\prepare_real_dataset.py --input-root data\合同数据-2026.3.12 --output Contract_Review_System/v1/data/real_eval_dataset_full.json --all-paragraphs

conda activate langchain; python Contract_Review_System\v1\scripts\run_formal_review.py --data-root data\合同数据-2026.3.12 --test-prefix 1- --knowledge-prefixes 2- 3- --output-root Contract_Review_System/v1/outputs/formal_runs --all-paragraphs --top-k 5 --eval-dataset Contract_Review_System/v1/data/real_eval_dataset_full.json

conda activate langchain; python Contract_Review_System\v1\scripts\run_formal_review.py --data-root data\合同数据-2026.3.12 --test-prefix 1- --knowledge-prefixes 2- 3- --output-root Contract_Review_System/v1/outputs/formal_runs --max-paragraphs 20 --min-paragraph-chars 50 --top-k 5 --eval-dataset Contract_Review_System/v1/data/real_eval_dataset_full.json
