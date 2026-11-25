import json
import os
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError

s3 = boto3.client("s3")
BUCKET_NAME = os.environ.get("BUCKET_NAME", "equipment-loans-theo")
PREFIX = "loans/"
ALLOWED_STATUSES = {"ACTIVE", "RETURNED"}


def build_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def get_object_key(loan_id: str) -> str:
    return f"{PREFIX}{loan_id}.json"


def object_exists(key: str) -> bool:
    try:
        s3.head_object(Bucket=BUCKET_NAME, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise


def lambda_handler(event, context):
    # Lambda Function URL uses Payload Format 2.0
    http_info = event.get("requestContext", {}).get("http", {})
    method = http_info.get("method", "GET")
    raw_path = event.get("rawPath", "/loans").rstrip("/")

    # Parse /loans vs /loans/{loan_id}
    parts = [p for p in raw_path.split("/") if p]
    if not parts or parts[0] != "loans" or len(parts) > 2:
        return build_response(404, {"error": f"Route {raw_path} not found"})

    loan_id = parts[1] if len(parts) == 2 else None

    try:
        # 1. CREATE: POST /loans
        if method == "POST" and not loan_id:
            body = json.loads(event.get("body") or "{}")
            if (
                not body.get("loan_id")
                or not body.get("item_name")
                or not body.get("borrower_name")
            ):
                return build_response(
                    400,
                    {"error": "loan_id, item_name, and borrower_name are required"},
                )

            new_id = str(body["loan_id"])
            key = get_object_key(new_id)
            if object_exists(key):
                return build_response(409, {"error": f"Loan {new_id} already exists"})

            status = str(body.get("status", "ACTIVE")).upper()
            if status not in ALLOWED_STATUSES:
                return build_response(
                    400,
                    {"error": f"Invalid status. Allowed values: {sorted(ALLOWED_STATUSES)}"},
                )

            item = {
                "loan_id": new_id,
                "item_name": str(body["item_name"]),
                "borrower_name": str(body["borrower_name"]),
                "status": status,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            s3.put_object(
                Bucket=BUCKET_NAME,
                Key=key,
                Body=json.dumps(item),
                ContentType="application/json",
            )
            return build_response(201, {"message": "Loan created", "data": item})

        # 2. READ: GET /loans or GET /loans/{loan_id}
        elif method == "GET":
            if loan_id:
                key = get_object_key(loan_id)
                try:
                    res = s3.get_object(Bucket=BUCKET_NAME, Key=key)
                    item = json.loads(res["Body"].read().decode("utf-8"))
                    return build_response(200, {"data": item})
                except ClientError as e:
                    if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                        return build_response(404, {"error": f"Loan {loan_id} not found"})
                    raise

            # List all objects under loans/
            paginator = s3.get_paginator("list_objects_v2")
            items = []
            for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=PREFIX):
                for obj in page.get("Contents", []):
                    if obj["Key"].endswith(".json"):
                        res = s3.get_object(Bucket=BUCKET_NAME, Key=obj["Key"])
                        items.append(json.loads(res["Body"].read().decode("utf-8")))

            return build_response(200, {"count": len(items), "items": items})

        # 3. UPDATE: PUT /loans/{loan_id}
        elif method == "PUT" and loan_id:
            key = get_object_key(loan_id)
            try:
                res = s3.get_object(Bucket=BUCKET_NAME, Key=key)
                item = json.loads(res["Body"].read().decode("utf-8"))
            except ClientError as e:
                if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                    return build_response(404, {"error": f"Loan {loan_id} not found"})
                raise

            body = json.loads(event.get("body") or "{}")
            new_status = str(body.get("status", "RETURNED")).upper()
            if new_status not in ALLOWED_STATUSES:
                return build_response(
                    400,
                    {"error": f"Invalid status. Allowed values: {sorted(ALLOWED_STATUSES)}"},
                )

            item["status"] = new_status
            s3.put_object(
                Bucket=BUCKET_NAME,
                Key=key,
                Body=json.dumps(item),
                ContentType="application/json",
            )
            return build_response(200, {"message": "Loan updated", "data": item})

        # 4. DELETE: DELETE /loans/{loan_id}
        elif method == "DELETE" and loan_id:
            key = get_object_key(loan_id)
            if not object_exists(key):
                return build_response(404, {"error": f"Loan {loan_id} not found"})

            s3.delete_object(Bucket=BUCKET_NAME, Key=key)
            return build_response(200, {"message": f"Loan {loan_id} deleted"})

        return build_response(405, {"error": f"Method {method} not allowed for {raw_path}"})

    except ClientError as e:
        return build_response(500, {"error": e.response["Error"]["Message"]})
    except Exception as e:
        return build_response(500, {"error": str(e)})