import json
import os
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ.get("TABLE_NAME", "EquipmentLoans")
table = dynamodb.Table(TABLE_NAME)

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


def lambda_handler(event, context):
    # Supports both API Gateway HTTP API (v2) and REST API (v1) event formats
    request_context = event.get("requestContext", {})
    http_info = request_context.get("http", {})
    method = http_info.get("method") or event.get("httpMethod", "GET")
    path_params = event.get("pathParameters") or {}
    loan_id = path_params.get("loan_id")

    try:
        # 1. CREATE: POST /loans
        if method == "POST":
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

            status = str(body.get("status", "ACTIVE")).upper()
            if status not in ALLOWED_STATUSES:
                return build_response(
                    400,
                    {"error": f"Invalid status. Allowed values: {sorted(ALLOWED_STATUSES)}"},
                )

            item = {
                "loan_id": str(body["loan_id"]),
                "item_name": str(body["item_name"]),
                "borrower_name": str(body["borrower_name"]),
                "status": status,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            try:
                table.put_item(
                    Item=item,
                    ConditionExpression="attribute_not_exists(loan_id)",
                )
            except ClientError as e:
                if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    return build_response(
                        409, {"error": f"Loan {item['loan_id']} already exists"}
                    )
                raise

            return build_response(201, {"message": "Loan created", "data": item})

        # 2. READ: GET /loans or GET /loans/{loan_id}
        elif method == "GET":
            if loan_id:
                res = table.get_item(Key={"loan_id": loan_id})
                item = res.get("Item")
                if not item:
                    return build_response(404, {"error": f"Loan {loan_id} not found"})
                return build_response(200, {"data": item})

            res = table.scan()
            items = res.get("Items", [])
            return build_response(200, {"count": len(items), "items": items})

        # 3. UPDATE: PUT /loans/{loan_id}
        elif method == "PUT":
            if not loan_id:
                return build_response(400, {"error": "loan_id path parameter is required"})

            body = json.loads(event.get("body") or "{}")
            new_status = str(body.get("status", "RETURNED")).upper()
            if new_status not in ALLOWED_STATUSES:
                return build_response(
                    400,
                    {"error": f"Invalid status. Allowed values: {sorted(ALLOWED_STATUSES)}"},
                )

            try:
                res = table.update_item(
                    Key={"loan_id": loan_id},
                    UpdateExpression="SET #s = :status",
                    ConditionExpression="attribute_exists(loan_id)",
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={":status": new_status},
                    ReturnValues="ALL_NEW",
                )
            except ClientError as e:
                if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                    return build_response(404, {"error": f"Loan {loan_id} not found"})
                raise

            return build_response(
                200, {"message": "Loan updated", "data": res.get("Attributes")}
            )

        # 4. DELETE: DELETE /loans/{loan_id}
        elif method == "DELETE":
            if not loan_id:
                return build_response(400, {"error": "loan_id path parameter is required"})

            table.delete_item(Key={"loan_id": loan_id})
            return build_response(200, {"message": f"Loan {loan_id} deleted"})

        return build_response(405, {"error": f"Method {method} not allowed"})

    except ClientError as e:
        return build_response(500, {"error": e.response["Error"]["Message"]})
    except Exception as e:
        return build_response(500, {"error": str(e)})