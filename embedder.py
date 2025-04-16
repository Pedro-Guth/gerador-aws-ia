import os
import boto3
from langchain_aws import BedrockEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
import fitz  # PyMuPDF

# Inicializa Bedrock embeddings
def get_titan_embedder():
    bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
    return BedrockEmbeddings(client=bedrock, model_id="amazon.titan-embed-text-v2:0")

def extract_text_from_pdf(path):
    text = ""
    doc = fitz.open(path)
    for page in doc:
        text += page.get_text()
    return text

def load_documents(folder="docs"):
    docs = []
    for filename in os.listdir(folder):
        path = os.path.join(folder, filename)

        if filename.endswith(".txt") or filename.endswith(".md"):
            with open(path, "r") as f:
                text = f.read()
        elif filename.endswith(".pdf"):
            text = extract_text_from_pdf(path)
        else:
            continue

        if text.strip():
            docs.append(Document(page_content=text, metadata={"source": filename}))
    return docs


def index_documents():
    documents = load_documents()
    if not documents:
        print("Nenhum documento encontrado em 'docs/'.")
        return

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(documents)
    
    print(f"🔹 Total de documentos: {len(documents)}")
    print(f"🔹 Total de chunks gerados: {len(chunks)}")

    if not chunks:
        print("Nenhum chunk gerado após dividir os documentos.")
        return

    embedder = get_titan_embedder()
    db = FAISS.from_documents(chunks, embedder)
    db.save_local("faiss_index")
    print("✅ Index criado com sucesso!")


if __name__ == "__main__":
    index_documents()
