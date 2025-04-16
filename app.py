import os
import json
import boto3
import subprocess
import re
from datetime import datetime
from flask import Flask, render_template, request, send_from_directory
from langchain_community.vectorstores import FAISS
from embedder import get_titan_embedder
import fitz 

app = Flask(__name__)
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

def recuperar_contexto_relevante(pergunta):
    db = FAISS.load_local("faiss_index", get_titan_embedder(), allow_dangerous_deserialization=True)
    docs = db.similarity_search(pergunta, k=4)

    for i, doc in enumerate(docs):
        print(f"\n--- Documento {i+1} ---")
        print(f"Fonte: {doc.metadata.get('source')}")
        print(doc.page_content[:50])  # Print 500 primeiros caracteres

    contexto = "\n\n".join([doc.page_content for doc in docs])
    return contexto

def limpar_classes_para_rag():
    with open("docs/aws_classes.txt") as f:
        linhas = f.readlines()
    classes = []
    for linha in linhas:
        linha = linha.strip()
        if linha.startswith("diagrams.aws.") and "(" not in linha:
            partes = linha.split(".")
            classe = partes[-1]
            modulo = partes[2]
            classes.append(f"{classe} ({modulo})")
    return "\n".join(classes)

def corrigir_imports(codigo: str) -> str:
    # Carrega mapeamento de classe -> módulo
    classe_modulo = {}
    with open("docs/aws_classes.txt") as f:
        for linha in f:
            if "," in linha:
                classe, modulo = linha.strip().split(",")
                classe_modulo[classe] = modulo

    # Detecta as classes usadas no código
    classes_usadas = set()
    for linha in codigo.splitlines():
        match = re.findall(r"([A-Z][a-zA-Z0-9]+)\(", linha)
        for classe in match:
            if classe in classe_modulo:
                classes_usadas.add(classe)

    # Gera os imports base e específicos
    modulos_usados = set(classe_modulo[c] for c in classes_usadas)
    bloco_imports = [
        "from diagrams import Diagram"
    ] + [f"from diagrams.aws.{mod} import *" for mod in sorted(modulos_usados)]

    # Remove todos os imports antigos e insere o novo bloco
    linhas = codigo.splitlines()
    linhas_sem_imports = [l for l in linhas if not l.startswith("from diagrams")]
    codigo_final = "\n".join(bloco_imports) + "\n\n" + "\n".join(linhas_sem_imports)

    return codigo_final

def substituir_imports_completos(filepath="temp_diagram.py"):
    bloco_imports = """from diagrams import Diagram
from diagrams.aws.analytics import *
from diagrams.aws.compute import *
from diagrams.aws.cost import *
from diagrams.aws.database import *
from diagrams.aws.devtools import *
from diagrams.aws.general import *
from diagrams.aws.integration import *
from diagrams.aws.iot import *
from diagrams.aws.management import *
from diagrams.aws.migration import *
from diagrams.aws.ml import *
from diagrams.aws.network import *
from diagrams.aws.security import *
from diagrams.aws.storage import *"""

    with open(filepath, "r") as f:
        linhas = f.readlines()

    linhas_sem_imports = [linha for linha in linhas if not linha.startswith("from diagrams")]

    with open(filepath, "w") as f:
        f.write(bloco_imports + "\n\n" + "".join(linhas_sem_imports))

def gerar_codigo_diagrama(prompt_usuario):
    contexto = recuperar_contexto_relevante(prompt_usuario)
    classes_validas = limpar_classes_para_rag()

    prompt_final = f"""
Você é um gerador de código Python usando a biblioteca diagrams para criar arquiteturas da AWS.

Regras:
- Gere apenas o código Python, sem explicações.
- Use SEMPRE os imports abaixo:
from diagrams import Diagram
from diagrams.aws.analytics import *
from diagrams.aws.compute import *
from diagrams.aws.database import *
from diagrams.aws.general import *
from diagrams.aws.iot import *
from diagrams.aws.management import *
from diagrams.aws.migration import *
from diagrams.aws.ml import *
from diagrams.aws.network import *
from diagrams.aws.security import *
from diagrams.aws.storage import *

-Use exatamente esta linha no código:
with Diagram("Arquitetura AWS", outformat="png", filename="static/diagram", show=False):

-Agora, com base na documentação abaixo e no pedido do usuário, gere o código.

-Use apenas as classes listadas abaixo. Gere apenas o código Python, sem explicações:

CLASSES SUPORTADAS:
{classes_validas}

DOCUMENTAÇÃO DE CONTEXTO:
{contexto}

EXEMPLO CORRETO:
from diagrams import Diagram
from diagrams.aws.compute import EC2
from diagrams.aws.database import RDS

with Diagram("Arquitetura AWS", outformat="png", filename="static/diagram", show=False):
    ec2 = EC2("App Server")
    rds = RDS("Database")
    ec2 >> rds

PROMPT DO USUÁRIO:
{prompt_usuario}
"""

    response = bedrock.invoke_model(
        modelId="anthropic.claude-3-sonnet-20240229-v1:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "messages": [{"role": "user", "content": prompt_final}],
            "max_tokens": 1024,
            "anthropic_version": "bedrock-2023-05-31"
        })
    )

    resultado = json.loads(response["body"].read())
    codigo = resultado["content"][0]["text"]

    if codigo.startswith("```python"):
        codigo = codigo.split("```python")[1].split("```")[0].strip()

    return codigo

def corrigir_codigo(codigo):
    substituicoes = {
        "DynamoDB(": "DynamodbTable(",
        "DynamoDBTable(": "DynamodbTable(",
        "KinesisStream(": "KinesisDataStreams(",
        "API_Gateway(": "APIGateway(",
        "API_GW(": "APIGateway(",
        "AutoScalingGroup(": "AutoScaling(",
        "AuroraMySQL(": "Aurora(",
        "AuroraPostgreSQL(": "Aurora(",
        "ElastiCacheRedis(": "ElastiCache(",
        "ApplicationLoadBalancer(": "ElbApplicationLoadBalancer(",
        "IoTHub(": "IotCore(",
    }

    for errado, certo in substituicoes.items():
        codigo = codigo.replace(errado, certo)

    # Bloco padrão de imports
    bloco_import = """from diagrams import Diagram
from diagrams.aws.compute import *
from diagrams.aws.database import *
from diagrams.aws.network import *
from diagrams.aws.storage import *
from diagrams.aws.integration import *
from diagrams.aws.ml import *
from diagrams.aws.security import *
from diagrams.aws.management import *"""

    # Remove imports antigos
    linhas = codigo.splitlines()
    linhas_filtradas = [linha for linha in linhas if not linha.startswith("from diagrams")]
    codigo_sem_import = "\n".join(linhas_filtradas)

    # Substitui corretamente qualquer linha 'with Diagram(...)' por uma linha fixa
    codigo_corrigido = re.sub(
        r'with Diagram\(.*?\):',
        'with Diagram("Arquitetura AWS", outformat="png", filename="static/diagram", show=False):',
        codigo_sem_import
    )

    return f"{bloco_import}\n\n{codigo_corrigido}"

def gerar_cloudformation(prompt_usuario):
    contexto = recuperar_contexto_relevante(prompt_usuario)

    prompt_final = f"""
Você é um gerador de infraestrutura como código (IaC) especializado em AWS.

Regras:
- Gere apenas o template em YAML, sem explicações.
- O código deve estar no formato válido do AWS CloudFormation.
- Use nomes genéricos nos recursos.

Baseado na documentação abaixo e no pedido do usuário, gere o template:

DOCUMENTAÇÃO DE CONTEXTO:
{contexto}

PROMPT DO USUÁRIO:
{prompt_usuario}
"""

    response = bedrock.invoke_model(
        modelId="anthropic.claude-3-sonnet-20240229-v1:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "messages": [{"role": "user", "content": prompt_final}],
            "max_tokens": 2048,
            "anthropic_version": "bedrock-2023-05-31"
        })
    )

    resultado = json.loads(response["body"].read())
    yaml_texto = resultado["content"][0]["text"]

    if yaml_texto.startswith("```yaml"):
        yaml_texto = yaml_texto.split("```yaml")[1].split("```")[0].strip()

    return yaml_texto

@app.route("/", methods=["GET", "POST"])
def index():
    codigo = ""
    imagem_gerada = False
    timestamp = datetime.now().timestamp()
    cloudformation = ""

    if request.method == "POST":
        prompt = request.form["prompt"]
        codigo = gerar_codigo_diagrama(prompt)
        codigo = corrigir_codigo(codigo)             # corrige nomes incorretos
        codigo = corrigir_imports(codigo)            # gera blocos de import corretos
        cloudformation = gerar_cloudformation(prompt)

        with open("temp_diagram.py", "w") as f:
            f.write(codigo)
        # Substitui os imports
        substituir_imports_completos("temp_diagram.py")

        try:
            subprocess.run(["python3", "temp_diagram.py"], check=True)
            imagem_gerada = True
        except Exception as e:
            codigo += f"\n\n# ERRO AO EXECUTAR: {e}"

    return render_template(
        "index.html",
        codigo=codigo,
        imagem_gerada=imagem_gerada,
        cloudformation=cloudformation,
        timestamp=int(timestamp)
    )

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

if __name__ == "__main__":
    app.run(debug=True)
