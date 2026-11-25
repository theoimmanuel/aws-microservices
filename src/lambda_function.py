import base64
import json
import os
import re
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

s3 = boto3.client("s3")
BUCKET = os.environ["BUCKET_NAME"]
PREFIX = "loans/"
VALID_STATUS = ("ACTIVE", "RETURNED")
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def build_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def key_for(loan_id):
    return f"{PREFIX}{loan_id}.json"


def read_loan(loan_id):
    """Return the loan as a dict, or None if it does not exist."""
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=key_for(loan_id))
        return json.loads(obj["Body"].read())
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return None
        raise


def write_loan(loan):
    s3.put_object(
        Bucket=BUCKET,
        Key=key_for(loan["loan_id"]),
        Body=json.dumps(loan).encode("utf-8"),
        ContentType="application/json",
    )


def list_loans():
    loans = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX):
        for obj in page.get("Contents", []):
            data = s3.get_object(Bucket=BUCKET, Key=obj["Key"])
            loans.append(json.loads(data["Body"].read()))
    return loans


def parse_body(event):
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    return json.loads(raw)


def lambda_handler(event, context):
    # Function URL events use payload format 2.0: method and path are
    # in requestContext.http.method and rawPath (no pathParameters).
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    parts = [p for p in event.get("rawPath", "/").split("/") if p]

    if not parts or parts[0] != "loans" or len(parts) > 2:
        return build_response(404, {"error": "Not found"})
    loan_id = parts[1] if len(parts) == 2 else None
    if loan_id and not ID_PATTERN.match(loan_id):
        return build_response(400, {"error": "Invalid loan_id"})

    try:
        # 1. CREATE: POST /loans
        if method == "POST" and loan_id is None:
            body = parse_body(event)
            for field in ("loan_id", "item_name", "borrower_name"):
                if not body.get(field):
                    return build_response(400, {
                        "error": "loan_id, item_name, and borrower_name are required"})
            new_id = str(body["loan_id"])
            if not ID_PATTERN.match(new_id):
                return build_response(400, {"error": "Invalid loan_id"})
            status = body.get("status", "ACTIVE")
            if status not in VALID_STATUS:
                return build_response(400, {"error": "status must be ACTIVE or RETURNED"})
            if read_loan(new_id) is not None:
                return build_response(409, {"error": f"Loan {new_id} already exists"})

            loan = {
                "loan_id": new_id,
                "item_name": str(body["item_name"]),
                "borrower_name": str(body["borrower_name"]),
                "status": status,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            write_loan(loan)
            return build_response(201, {"message": "Loan created", "data": loan})

        # 2. READ: GET /loans or GET /loans/{loan_id}
        if method == "GET":
            if loan_id:
                loan = read_loan(loan_id)
                if loan is None:
                    return build_response(404, {"error": f"Loan {loan_id} not found"})
                return build_response(200, {"data": loan})
            loans = list_loans()
            return build_response(200, {"count": len(loans), "items": loans})

        # 3. UPDATE: PUT /loans/{loan_id}
        if method == "PUT" and loan_id:
            body = parse_body(event)
            new_status = body.get("status", "RETURNED")
            if new_status not in VALID_STATUS:
                return build_response(400, {"error": "status must be ACTIVE or RETURNED"})
            loan = read_loan(loan_id)
            if loan is None:
                return build_response(404, {"error": f"Loan {loan_id} not found"})
            loan["status"] = new_status
            write_loan(loan)
            return build_response(200, {"message": "Loan updated", "data": loan})

        # 4. DELETE: DELETE /loans/{loan_id}
        if method == "DELETE" and loan_id:
            if read_loan(loan_id) is None:
                return build_response(404, {"error": f"Loan {loan_id} not found"})
            s3.delete_object(Bucket=BUCKET, Key=key_for(loan_id))
            return build_response(200, {"message": f"Loan {loan_id} deleted"})

        return build_response(405, {"error": f"Method {method} not allowed here"})

    except json.JSONDecodeError:
        return build_response(400, {"error": "Request body must be valid JSON"})
    except ClientError as e:
        return build_response(500, {"error": e.response["Error"]["Message"]})
    except Exception as e:
        return build_response(500, {"error": str(e)})