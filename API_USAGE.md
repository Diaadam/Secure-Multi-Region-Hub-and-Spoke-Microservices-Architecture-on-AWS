# Flask User API - Detailed Usage Guide

This guide explains how to run and use the API implemented in `simple.py`.

## 1) Overview

Base URL when running locally:

- `http://localhost:5000`

Current implemented endpoints:

- `GET /`
- `GET /help`
- `GET /getAllUsers`
- `GET /getUserByEmail/<email>`
- `GET /getUserById/<id>`
- `POST /createUser`
- `PATCH /updateUser/<id>`
- `PUT /updateUser/<id>`

## 2) Run The API

From the project folder:

```powershell
python simple.py
```

Flask will start in debug mode and listen on port 5000 by default.

## 3) Response Format

All handlers return a common structure:

```json
{
  "statusCode": 200,
  "headers": {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type"
  },
  "body": "...JSON string..."
}
```

Important note:

- `body` is a stringified JSON payload, not a raw JSON object.
- In Postman tests, parse `body` if needed.

## 4) Endpoints In Detail

### 4.1 Health Check

- Method: `GET`
- Path: `/`
- Purpose: Confirm app is running.

Example:

```http
GET http://localhost:5000/
```

Expected response body content:

```text
OK
```

---

### 4.2 Help Page

- Method: `GET`
- Path: `/help`
- Purpose: Render this API guide (`API_USAGE.md`) in a browser-friendly HTML page.

Example:

```http
GET http://localhost:5000/help
```

Behavior:

- Reads `API_USAGE.md` from the project folder.
- If the `markdown` package is available, renders full Markdown to HTML.
- If `markdown` is unavailable, shows safe preformatted text fallback.
- If `API_USAGE.md` is missing, returns `404` with a short message.

---

### 4.3 Get All Users

- Method: `GET`
- Path: `/getAllUsers`
- Purpose: Reads all items from DynamoDB table using scan.

Example:

```http
GET http://localhost:5000/getAllUsers
```

Success response body (`body` field) is typically a JSON array of items.

---

### 4.4 Get User By Email

- Method: `GET`
- Path: `/getUserByEmail/<email>`
- Purpose: Fetch a user by email key.

Example:

```http
GET http://localhost:5000/getUserByEmail/EMAIL%23user2@example.com
```

Use URL encoding when needed:

- `#` becomes `%23`

Current code note:

- This route currently uses `table.get_item(...)` with `IndexName` and `KeyConditionExpression`.
- In boto3, that pattern is usually used with `table.query(...)`, not `get_item(...)`.
- If this route fails, update implementation to query on GSI.

---

### 4.5 Get User By Id

- Method: `GET`
- Path: `/getUserById/<id>`
- Purpose: Fetch user by id value in URL.

Examples:

```http
GET http://localhost:5000/getUserById/USER%232
GET http://localhost:5000/getUserById/2
```

Current code behavior:

- This route has the same boto3 method caveat as `getUserByEmail`.

---

### 4.6 Create User

- Method: `POST`
- Path: `/createUser`
- Purpose: Create a new user item with generated/normalized key attributes.

#### Required fields

- `id`
- `email`

#### How keys are built

- `PK`:
  - if `id` starts with `USER#`, keep as-is
  - else set to `USER#<id>`
- `SK`:
  - if `SK` exists in request body, use it
  - else auto-generate with current UTC timestamp (`...Z`)
- `GSI1PK`:
  - if `GSI1PK` exists in request body, use it
  - else set from email as `EMAIL#<email>` unless email already starts with `EMAIL#`
- `GSI1SK`: always set to `PK`

#### Duplicate protection

The route writes using:

- `ConditionExpression='attribute_not_exists(PK) AND attribute_not_exists(SK)'`

This prevents creating the same `PK+SK` item twice.

#### Postman example

- Method: `POST`
- URL: `http://localhost:5000/createUser`
- Headers: `Content-Type: application/json`
- Body:

```json
{
  "id": "2",
  "email": "user2@example.com",
  "name": "Test User 2",
  "address": {
    "street": "200 Main St",
    "city": "Metropolis",
    "zip": "10002"
  }
}
```

Equivalent curl:

```bash
curl -X POST "http://localhost:5000/createUser" \
  -H "Content-Type: application/json" \
  -d '{"id":"2","email":"user2@example.com","name":"Test User 2","address":{"street":"200 Main St","city":"Metropolis","zip":"10002"}}'
```

#### Success response

- `statusCode`: `201`
- `body`: created item (JSON string)

#### Error responses

- `400` if:
  - body empty or not object
  - `id` missing
  - `email` missing
- `409` if same `PK+SK` already exists
- `500` for unexpected AWS/client exceptions

---

### 4.7 Update User (Partial Update)

- Methods: `PATCH` or `PUT`
- Path: `/updateUser/<id>`
- Purpose: Update only provided attributes while keeping other attributes unchanged.

#### How target user is resolved

- `id` from path is normalized to PK:
  - If id starts with `USER#`, use as-is
  - Else convert to `USER#<id>`
- API queries by `PK` with `Limit=1`, then uses found `SK`.
- Update is done with key pair `{PK, SK}`.

#### Important restrictions

The API rejects updates to key attributes:

- `PK`
- `SK`

If any of these fields are included in body, response is `400`.

#### Request requirements

- `Content-Type: application/json`
- Body must be a non-empty JSON object.

#### Postman example

- Method: `PATCH`
- URL: `http://localhost:5000/updateUser/2`
- Headers: `Content-Type: application/json`
- Body:

```json
{
  "name": "Updated User Name",
  "address": {
    "street": "201 Main St",
    "city": "Cairo",
    "zip": "10002"
  },
  "entityType": "User"
}
```

Equivalent curl:

```bash
curl -X PATCH "http://localhost:5000/updateUser/2" \
  -H "Content-Type: application/json" \
  -d '{"name":"Updated User Name","address":{"street":"201 Main St","city":"Cairo","zip":"10002"},"entityType":"User"}'
```

#### Success response

- `statusCode`: `200`
- `body`: updated item attributes (JSON string)

#### Error responses

- `400` if:
  - path id missing
  - body empty or not object
  - forbidden key attributes included
- `404` if user does not exist for resolved PK
- `500` for unexpected AWS/client exceptions

## 5) Postman Quick Checklist

Before sending `POST /createUser`:

1. Method must be `POST`.
2. URL must be `/createUser`.
3. Header must include `Content-Type: application/json`.
4. Body must include at least `id` and `email`.

Before sending `PATCH /updateUser/<id>`:

1. Use the correct route (`/updateUser/...`), not `/getUserById/...`.
2. Method must be `PATCH` (or `PUT`).
3. Header must include `Content-Type: application/json`.
4. Send update fields in Body, not URL params.
5. Keep `PK` and `SK` out of request body.

## 6) Common Troubleshooting

### 405 Method Not Allowed

Cause:

- Sending `PATCH` to a GET-only route like `/getUserById/<id>`.

Fix:

- Use `PATCH /updateUser/<id>`.

### ValidationException: provided key element does not match schema

Cause:

- Using wrong key shape for table key schema.

Fix in current implementation:

- Already handled by deriving `{PK, SK}` before `update_item`.

### Empty result when email/id includes '#'

Cause:

- `#` in URL is treated as fragment unless encoded.

Fix:

- Encode `#` as `%23`.

## 7) Data Model Notes

From your key definitions, table keys are:

- Partition key: `PK` (String)
- Sort key: `SK` (String)

GSI keys include:

- `GSI1PK`
- `GSI1SK`

When designing future routes:

- Use `query` for key-based searches and GSIs.
- Avoid `scan` for large tables whenever possible.
