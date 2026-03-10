#!/usr/bin/env python3
"""Simple RAG pipeline for contract review (DOCX with comments).

Features:
- Convert Windows path (e.g. E:\\...) to WSL-style path (/mnt/e/...)
- Extract main text and DOCX comments from the .docx (reads word/document.xml and word/comments.xml)
- Chunk text, create embeddings, build FAISS vectorstore, and run a RetrievalQA loop

Usage (WSL):
  python examples/rag-contract-review/contract_rag.py /mnt/e/Work/.../file.docx --index_dir ./index_dir

Environment:
- For OpenAI embeddings/LLM set `OPENAI_API_KEY` in env. You can switch to other embeddings/LLMs by editing the `get_embeddings` / `get_llm` helpers.
"""
from __future__ import annotations

import argparse
import os
import zipfile
import xml.etree.ElementTree as ET
from typing import List, Tuple
from dotenv import load_dotenv

try:
    from langchain.embeddings import OpenAIEmbeddings
    from langchain.vectorstores import FAISS
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain.chains import RetrievalQA
    from langchain.chat_models import ChatOpenAI
except Exception as e:  # pragma: no cover - helpful error when libs missing
    raise RuntimeError(
        "Missing langchain or related dependencies. Install requirements from examples/rag-contract-review/requirements.txt"
    ) from e


# load .env if present
load_dotenv()


def windows_to_wsl(path: str) -> str:
    # Convert Windows path like E:\\foo\\bar.docx to /mnt/e/foo/bar.docx
    if path.startswith("/"):
        return path
    path = path.replace('\\', '/')
    if len(path) >= 2 and path[1] == ':' and path[0].isalpha():
        drive = path[0].lower()
        return f"/mnt/{drive}" + path[2:]
    return path


def extract_docx_text_and_comments(path: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Return (document_text, [(author, comment_text), ...])"""
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    doc_text_parts: List[str] = []
    comments: List[Tuple[str, str]] = []

    with zipfile.ZipFile(path) as z:
        # document.xml
        if 'word/document.xml' in z.namelist():
            data = z.read('word/document.xml')
            root = ET.fromstring(data)
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            for p in root.findall('.//w:p', ns):
                texts = [t.text for t in p.findall('.//w:t', ns) if t.text]
                if texts:
                    doc_text_parts.append(''.join(texts))

        # comments.xml (optional)
        if 'word/comments.xml' in z.namelist():
            data = z.read('word/comments.xml')
            root = ET.fromstring(data)
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            for comment in root.findall('.//w:comment', ns):
                author = comment.attrib.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}author', '')
                # collect paragraph text inside comment
                parts = []
                for p in comment.findall('.//w:p', ns):
                    texts = [t.text for t in p.findall('.//w:t', ns) if t.text]
                    if texts:
                        parts.append(''.join(texts))
                comments.append((author, '\n'.join(parts)))

    return '\n\n'.join(doc_text_parts), comments


def build_vectorstore(texts: List[str], index_dir: str, embedding_model: str | None = None):
    if embedding_model:
        embeddings = OpenAIEmbeddings(model=embedding_model)
    else:
        embeddings = OpenAIEmbeddings()
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    docs = []
    for t in texts:
        docs.extend(text_splitter.split_text(t))

    if os.path.exists(index_dir):
        # load if exists
        return FAISS.load_local(index_dir, embeddings)

    vs = FAISS.from_texts(docs, embeddings)
    vs.save_local(index_dir)
    return vs


def get_llm(llm_model: str | None = None):
    model = llm_model or os.getenv('OPENAI_LLM_MODEL', 'qianwen-model-name')
    return ChatOpenAI(temperature=0, model_name=model)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('docx_path', help='Path to docx (Windows path OK, will be converted)')
    parser.add_argument('--index_dir', default='./contract_index', help='Directory to save/load index')
    parser.add_argument('--llm-model', default=None, help='LLM model name (overrides OPENAI_LLM_MODEL)')
    parser.add_argument('--embed-model', default=None, help='Embedding model name (overrides OPENAI_EMBEDDING_MODEL)')
    args = parser.parse_args()

    path = windows_to_wsl(args.docx_path)
    print(f'Loading {path}...')
    doc_text, comments = extract_docx_text_and_comments(path)

    texts = [doc_text]
    for i, (author, c) in enumerate(comments, start=1):
        texts.append(f'COMMENT #{i} by {author}:\n{c}')

    print(f'Found {len(texts)} text blocks (including comments). Building / loading vectorstore...')
    embed_model = args.embed_model or os.getenv('OPENAI_EMBEDDING_MODEL')
    vs = build_vectorstore(texts, args.index_dir, embedding_model=embed_model)

    retriever = vs.as_retriever(search_kwargs={'k': 4})
    llm_model = args.llm_model or os.getenv('OPENAI_LLM_MODEL')
    qa = RetrievalQA.from_chain_type(llm=get_llm(llm_model), chain_type='stuff', retriever=retriever)

    print('\nIndex ready. Ask contract-review questions. Type `exit` to quit.')
    while True:
        q = input('\nQuestion> ').strip()
        if not q or q.lower() in ('exit', 'quit'):
            break
        prompt = (
            'You are a contract review assistant. Identify risk points, issues, and suggest improvements or mitigations. ' + q
        )
        ans = qa.run(prompt)
        print('\n=== ANSWER ===\n')
        print(ans)


if __name__ == '__main__':
    main()
