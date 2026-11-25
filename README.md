# Serverless Equipment Loan Management API (Track C)

A serverless CRUD REST API built on AWS (**API Gateway**, **Lambda**, and **DynamoDB**) for tracking laboratory and campus equipment loans.

## Architecture

```mermaid
flowchart LR
    Client(["External Client<br/>(curl / Postman / Web UI)"])

    subgraph AWS ["AWS Cloud (us-east-1)"]
        direction LR
        APIGW["Amazon API Gateway<br/>(HTTP API)<br/>/loans, /loans/{loan_id}"]
        IAM[["IAM Execution Role (LabRole)<br/>DynamoDB CRUD + CloudWatch Logs"]]
        Lambda["AWS Lambda<br/>loans-crud-handler<br/>Python 3.12"]
        DDB[("Amazon DynamoDB<br/>EquipmentLoans<br/>PK: loan_id (String)<br/>On-Demand")]
        CW["Amazon CloudWatch Logs<br/>/aws/lambda/loans-crud-handler"]

        Client -- "1. HTTPS (TLS)<br/>JSON" --> APIGW
        APIGW -- "2. Proxy invoke" --> Lambda
        IAM -. "3. Assumed by Lambda" .-> Lambda
        Lambda <-- "4. CRUD via boto3" --> DDB
        Lambda -- "5. Logs and metrics" --> CW
        APIGW -- "6. Status + JSON" --> Client
    end