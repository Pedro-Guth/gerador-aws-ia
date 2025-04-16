from diagrams import Diagram
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
from diagrams.aws.storage import *




with Diagram("Arquitetura AWS", outformat="png", filename="static/diagram", show=False):
    source = Kinesis("Kinesis Data Stream")
    lambda_function = Lambda("Lambda Function")
    glue_job = Glue("Glue ETL Job")
    data_store = S3("Data Store")

    source >> lambda_function >> glue_job >> data_store