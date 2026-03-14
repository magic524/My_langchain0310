from docling.document_converter import DocumentConverter
from docling.datamodel.pipeline_options import (
    AcceleratorDevice,
    AcceleratorOptions,
    PdfPipelineOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat

source = r"W:\a_study\Other\Deep_Learning\LLM\50_2\Dataset\train_dataset.pdf"  # PDF path or URL

## ****************************** 加速器选择 ***********************************
# Explicitly set the accelerator
# accelerator_options = AcceleratorOptions(
#     num_threads=8, device=AcceleratorDevice.AUTO
# )
# accelerator_options = AcceleratorOptions(
#     num_threads=8, device=AcceleratorDevice.CPU
# )
# accelerator_options = AcceleratorOptions(
#     num_threads=8, device=AcceleratorDevice.MPS
# )
accelerator_options = AcceleratorOptions(
    num_threads=8, device=AcceleratorDevice.CUDA
)

# easyocr doesnt support cuda:N allocation, defaults to cuda:0
# accelerator_options = AcceleratorOptions(num_threads=8, device="cuda:1")

pipeline_options = PdfPipelineOptions()
pipeline_options.accelerator_options = accelerator_options
# pipeline_options.do_ocr = True
pipeline_options.do_table_structure = True
pipeline_options.table_structure_options.do_cell_matching = True
##*******************************************************************************
converter = DocumentConverter(
    format_options={
        InputFormat.PDF: PdfFormatOption(
            pipeline_options=pipeline_options,
        )
    }
)

result = converter.convert(source)

parse_result = result.document.export_to_markdown( page_break_placeholder="--- PAGE BREAK ---", mark_annotations=True)
parse_result2 = result.document.export_to_html()
print(parse_result)
# 可转化的格式
# print(result.document.export_to_markdown())
# print(result.document.export_to_dict())
# print(result.document.export_to_pandas())
# print(result.document.export_to_element_tree())
# print(result.document.export_to_text())
print(result.document.export_to_html())
# print(result.document.export_to_doctags())
