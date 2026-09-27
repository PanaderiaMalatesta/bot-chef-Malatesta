"""Construye el indice de busqueda semantica sobre el recetario (data/recetas.md).

Se usa para que el agente pueda responder preguntas abiertas sobre como se hace
un producto (ingredientes, procedimiento), separado del costeo numerico exacto
que vive en tools.py / costeo_unitario.csv.
"""
from __future__ import annotations

from dotenv import load_dotenv
from langchain_cohere import CohereEmbeddings
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import MarkdownTextSplitter

from .paths import DATA_DIR

load_dotenv()

RECETAS_PATH = DATA_DIR / "recetas.md"
RECETAS_IMPORTADAS_PATH = DATA_DIR / "recetas_importadas.md"
INDEX_DIR = DATA_DIR / "index_recetas"


def build_index() -> FAISS:
    rutas = [RECETAS_PATH] + ([RECETAS_IMPORTADAS_PATH] if RECETAS_IMPORTADAS_PATH.exists() else [])
    documentos = []
    for ruta in rutas:
        documentos.extend(TextLoader(str(ruta), encoding="utf-8").load())

    splitter = MarkdownTextSplitter(chunk_size=800, chunk_overlap=100)
    chunks = splitter.split_documents(documentos)

    embeddings = CohereEmbeddings(model="embed-multilingual-v3.0")
    vectorstore = FAISS.from_documents(chunks, embeddings)
    vectorstore.save_local(str(INDEX_DIR))
    return vectorstore


def load_index() -> FAISS:
    embeddings = CohereEmbeddings(model="embed-multilingual-v3.0")
    return FAISS.load_local(str(INDEX_DIR), embeddings, allow_dangerous_deserialization=True)


if __name__ == "__main__":
    build_index()
    print(f"Indice creado en {INDEX_DIR}")
