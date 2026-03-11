#!/usr/bin/env python3
"""Simple RAG pipeline for contract review (DOCX with comments).0

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
import json
import numpy as np
import faiss
from dotenv import load_dotenv

try:
    # use the langchain-openai integration if available
    from langchain_openai import OpenAIEmbeddings
    from langchain_openai.chat_models import ChatOpenAI
except Exception as e:  # pragma: no cover - helpful error when libs missing
    raise RuntimeError(
        "Missing langchain_openai or related dependencies. Install requirements from examples/rag-contract-review/requirements.txt"
    ) from e


# simple utilities: numpy + faiss based vectorstore (lightweight)


def simple_text_splitter(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> List[str]:
    if not text:
        return []
    texts: List[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        texts.append(text[start:end])
        start = end - chunk_overlap if end < length else end
    return texts


# load .env if present
load_dotenv()

# allow DASHSCOPE_API_KEY in .env as alias for OPENAI_API_KEY
if not os.getenv('OPENAI_API_KEY') and os.getenv('DASHSCOPE_API_KEY'):
    os.environ['OPENAI_API_KEY'] = os.getenv('DASHSCOPE_API_KEY')


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
    os.makedirs(index_dir, exist_ok=True)
    # choose embedding model
    base_url = os.getenv('OPENAI_API_BASE')
    if base_url:
        # for OpenAI-compatible providers that don't support tokenized inputs
        kwargs = dict(check_embedding_ctx_length=False, encoding_format='float')
    else:
        kwargs = {}

    if embedding_model:
        embeddings = OpenAIEmbeddings(model=embedding_model, **kwargs)
    else:
        embeddings = OpenAIEmbeddings(**kwargs)

    # split into chunks
    docs: List[str] = []
    for t in texts:
        docs.extend(simple_text_splitter(t, chunk_size=1000, chunk_overlap=200))

    meta_path = os.path.join(index_dir, 'docs.json')
    index_path = os.path.join(index_dir, 'index.faiss')

    if os.path.exists(index_path) and os.path.exists(meta_path):
        # load
        index = faiss.read_index(index_path)
        with open(meta_path, 'r', encoding='utf-8') as f:
            docs = json.load(f)
        return {'index': index, 'docs': docs, 'embeddings': embeddings}

    # compute embeddings
    print('Computing embeddings for', len(docs), 'chunks...')
    vectors = []
    batch_size = 8
    for i in range(0, len(docs), batch_size):
        batch = embeddings.embed_documents(docs[i:i+batch_size])
        vectors.extend(batch)
    np_vectors = np.array(vectors, dtype='float32')
    # normalize for cosine similarity
    norms = np.linalg.norm(np_vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    np_vectors = np_vectors / norms

    dim = np_vectors.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(np_vectors)

    faiss.write_index(index, index_path)
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(docs, f, ensure_ascii=False)

    return {'index': index, 'docs': docs, 'embeddings': embeddings}


def get_llm(llm_model: str | None = None):
    model = llm_model or os.getenv('OPENAI_LLM_MODEL', 'qianwen-model-name')
    # ChatOpenAI uses 'model' param name in this integration
    return ChatOpenAI(temperature=0, model=model)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('docx_path', help='Path to docx (Windows path OK, will be converted)')
    parser.add_argument('--index_dir', default='./contract_index', help='Directory to save/load index')
    parser.add_argument('--llm-model', default=None, help='LLM model name (overrides OPENAI_LLM_MODEL)')
    parser.add_argument('--embed-model', default=None, help='Embedding model name (overrides OPENAI_EMBEDDING_MODEL)')
    parser.add_argument('--debug', action='store_true', help='Run a short debug call to verify API/base and print request ids')
    parser.add_argument('--auto', action='store_true', help='Run a preset batch of review questions non-interactively')
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

    index = vs['index']
    docs = vs['docs']
    embeddings = vs['embeddings']

    llm_model = args.llm_model or os.getenv('OPENAI_LLM_MODEL')
    llm = get_llm(llm_model)

    def mask_key(k: str | None) -> str:
        if not k:
            return '<missing>'
        return k[:4] + '...' + k[-4:]

    if args.debug:
        print('\n-- DEBUG INFO --')
        print('OPENAI_API_BASE=', os.getenv('OPENAI_API_BASE'))
        print('OPENAI_LLM_MODEL=', llm_model)
        print('OPENAI_EMBEDDING_MODEL=', embed_model)
        print('OPENAI_API_KEY=', mask_key(os.getenv('OPENAI_API_KEY')))

        # embeddings raw test
        try:
            emb = vs['embeddings']
            # call underlying client to capture provider response metadata when possible
            client = getattr(emb, 'client', None)
            if client is not None:
                print('\n-> testing embeddings API (one small call)')
                try:
                    # prefer passing explicit model when provider expects it
                    if embed_model:
                        resp = client.create(input=["debug ping"], model=embed_model)
                    else:
                        resp = client.create(input=["debug ping"])  # may return model-specific response
                except TypeError:
                    resp = client.create(input=["debug ping"])  # fallback
                try:
                    # attempt to print request id / model
                    if isinstance(resp, dict):
                        print('embeddings response keys:', list(resp.keys()))
                        rid = resp.get('request_id') or resp.get('id')
                        print('embeddings request_id:', rid)
                        # log to file
                        try:
                            with open(os.path.join(args.index_dir, 'debug_calls.log'), 'a', encoding='utf-8') as lf:
                                lf.write(f"EMBEDDING_TEST id={rid} model={embed_model}\n")
                        except Exception:
                            pass
                    else:
                        # pydantic models may have model_dump
                        d = getattr(resp, 'model_dump', lambda: None)()
                        print('embeddings response dump keys:', list(d.keys()) if d else repr(resp))
                        try:
                            rid = d.get('id')
                            with open(os.path.join(args.index_dir, 'debug_calls.log'), 'a', encoding='utf-8') as lf:
                                lf.write(f"EMBEDDING_TEST id={rid} model={embed_model}\n")
                        except Exception:
                            pass
                except Exception as e:
                    print('could not parse embeddings response metadata:', e)
            else:
                print('embeddings client not available to debug')
        except Exception as e:
            print('embeddings debug call failed:', e)

        # llm raw test
        try:
            print('\n-> testing LLM invoke (one small call)')
            resp = llm.invoke([('system', 'ping'), ('human', 'debug ping')])
            # try to extract response metadata
            meta = getattr(resp, 'response_metadata', None) or getattr(resp, 'usage_metadata', None) or getattr(resp, 'response', None)
            print('llm response type:', type(resp))
            print('llm response metadata:', meta)
            print('llm content snippet:', getattr(resp, 'content', str(resp))[:200])
            # log llm response id if available
            try:
                rid = None
                if isinstance(meta, dict):
                    rid = meta.get('id') or meta.get('request_id') or meta.get('chat_id')
                else:
                    rid = getattr(meta, 'id', None)
                with open(os.path.join(args.index_dir, 'debug_calls.log'), 'a', encoding='utf-8') as lf:
                    lf.write(f"LLM_TEST id={rid} model={llm_model}\n")
            except Exception:
                pass
        except Exception as e:
            print('llm debug call failed:', e)

    # auto mode: run preset questions non-interactively and log request ids
    if args.auto:
        preset_questions = [
            '请对当前已索引的合同做一次全面审查，按照“风险点 / 改进建议 / 关键条款定位”格式输出。',
            '甲乙双方信息是否完整？指出缺失项。',
            '履约期限和服务完成时间是否存在冲突？',
            '违约责任和争议解决条款是否明确？',
            '数据保护与保密义务是否充分？'
        ]
        for q in preset_questions:
            print('\nAuto-question:', q)
            # embed query and search
            q_vec = np.array(embeddings.embed_query(q), dtype='float32')
            q_vec = q_vec / np.linalg.norm(q_vec)
            D, I = index.search(np.expand_dims(q_vec, axis=0), 4)
            hits = [docs[int(i)] for i in I[0] if i != -1]
            context = '\n\n'.join(hits)

            system_msg = '你是合同审查助手。用提供的上下文识别风险点，给出改进建议，并定位相关条款。回答请简洁、中文。'
            human_prompt = f"上下文：\n{context}\n\n问题：{q}\n\n请在三个小节内回复：1) 风险点；2) 改进建议；3) 关键条款定位（如果能定位的话）。"

            try:
                resp = llm.invoke([('system', system_msg), ('human', human_prompt)])
                content = getattr(resp, 'content', str(resp))
                print('\n=== ANSWER ===\n')
                print(content)
                # log id
                try:
                    meta = getattr(resp, 'response_metadata', None) or getattr(resp, 'usage_metadata', None) or None
                    rid = None
                    if isinstance(meta, dict):
                        rid = meta.get('id') or meta.get('request_id')
                    else:
                        rid = getattr(meta, 'id', None)
                    with open(os.path.join(args.index_dir, 'debug_calls.log'), 'a', encoding='utf-8') as lf:
                        lf.write(f"AUTO_Q id={rid} model={llm_model} question={q}\n")
                except Exception:
                    pass
            except Exception as e:
                print('auto question failed:', e)

        return

    print('\nIndex ready. Ask contract-review questions. Type `exit` to quit.')
    while True:
        q = input('\nQuestion> ').strip()
        if not q or q.lower() in ('exit', 'quit'):
            break

        # embed query and search
        q_vec = np.array(embeddings.embed_query(q), dtype='float32')
        q_vec = q_vec / np.linalg.norm(q_vec)
        D, I = index.search(np.expand_dims(q_vec, axis=0), 4)
        hits = [docs[int(i)] for i in I[0] if i != -1]
        context = '\n\n'.join(hits)

        system_msg = '你是合同审查助手。用提供的上下文识别风险点，给出改进建议，并定位相关条款。回答请简洁、中文。'
        human_prompt = f"上下文：\n{context}\n\n问题：{q}\n\n请在三个小节内回复：1) 风险点；2) 改进建议；3) 关键条款定位（如果能定位的话）。"

        # invoke model
        try:
            resp = llm.invoke([('system', system_msg), ('human', human_prompt)])
            # .invoke returns an AIMessage-like object with .content
            content = getattr(resp, 'content', str(resp))
        except Exception as e:
            content = f'模型调用出错: {e}'

        print('\n=== ANSWER ===\n')
        print(content)
        # if debug, try to record response id/metadata
        if args.debug:
            try:
                meta = getattr(resp, 'response_metadata', None) or getattr(resp, 'usage_metadata', None) or None
                rid = None
                if isinstance(meta, dict):
                    rid = meta.get('id') or meta.get('request_id')
                else:
                    rid = getattr(meta, 'id', None)
                with open(os.path.join(args.index_dir, 'debug_calls.log'), 'a', encoding='utf-8') as lf:
                    lf.write(f"QA id={rid} model={llm_model} question={q}\n")
            except Exception:
                pass


if __name__ == '__main__':
    main()
