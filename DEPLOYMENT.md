```markdown
# Deployment Plan (AWS Track C - `us-east-1`)

## 1. Create DynamoDB Table
1. Navigate to **DynamoDB > Tables > Create table** in `us-east-1`.
2. Set **Table name** to `EquipmentLoans` and **Partition key** to `loan_id` (`String`).
3. Under **Table settings**, select **Customize settings** and set **Capacity mode** to **On-demand**.
4. Click **Create table** and wait until status is **Active**.

## 2. Create Lambda Function
1. Navigate to **Lambda > Create function > Author from scratch**.
2. Set **Function name** to `loans-crud-handler` and **Runtime** to **Python 3.12**.
3. Expand **Change default execution role**, choose **Use an existing role**, and select `LabRole`.
4. Click **Create function**, paste `src/lambda_function.py` into the code editor, and click **Deploy**.
5. Go to **Configuration > Environment variables > Edit > Add** and set key `TABLE_NAME` to `EquipmentLoans`.

## 3. Create API Gateway HTTP API
1. Navigate to **API Gateway > Create API > HTTP API > Build**.
2. Add a **Lambda** integration pointing to `loans-crud-handler` (`us-east-1`, payload format `2.0`).
3. Name the API `equipment-loans-api` and configure the following routes to target `loans-crud-handler`:
   * `POST /loans`
   * `GET /loans`
   * `GET /loans/{loan_id}`
   * `PUT /loans/{loan_id}`
   * `DELETE /loans/{loan_id}`
4. Keep stage `$default` with **Auto-deploy** enabled and click **Create**.
5. Copy the **Invoke URL** from the API details page.

## 4. Verification Commands

### Git Bash / Linux / macOS (`curl`)
```bash
# 1. Create a loan (POST)
curl -i -X POST "<YOUR_INVOKE_URL>/loans" \
  -H "Content-Type: application/json" \
  -d '{"loan_id": "LN-2026-002", "item_name": "Oscilloscope Rigol", "borrower_name": "Theo Sanyoto"}'

# 2. List all loans (GET)
curl -i -X GET "<YOUR_INVOKE_URL>/loans"

# 3. Update loan status (PUT)
curl -i -X PUT "<YOUR_INVOKE_URL>/loans/LN-2026-002" \
  -H "Content-Type: application/json" \
  -d '{"status": "RETURNED"}'

# 4. Delete loan (DELETE)
curl -i -X DELETE "<YOUR_INVOKE_URL>/loans/LN-2026-002"