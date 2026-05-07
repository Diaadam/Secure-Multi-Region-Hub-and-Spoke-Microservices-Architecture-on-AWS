# Flask User API - Detailed Usage Guide

This guide explains how to run and use the API implemented in `unified.py`.

## 1) Overview

Base URL when running locally:

- `http://localhost:5000`

Current implemented endpoints:

- `GET /`
- `GET /help`
- `GET /Users`
- `GET /Users/<email>`
- `GET /getUserById/<id>`
- `POST /Users`
- `PATCH /Users/<id>`
- `PUT /Users/<id>`

## 2) Run The API

From the project folder:

```powershell
python unified.py
```

Flask will start in debug mode and listen on port 5000 by default.

### Optional Cognito Provisioning

If you want `POST /Users` to also create the user in an AWS Cognito user pool, set this environment variable before starting the app:

- `COGNITO_USER_POOL_ID`

The app expects the raw Cognito UserPoolId value.

## 3) Response Format

All handlers now return a real Flask JSON response with the HTTP status code set on the response itself.

Important notes:

- The body is returned as JSON, not as a Lambda-style `{ statusCode, headers, body }` envelope.
- CORS headers are added by the application response helper.
- If you are using Postman or curl, read the response body directly as JSON.

## 4) Endpoints In Detail

### 4.1 Health Check

- Method: `GET`
- Path: `/`
- Purpose: Confirm the app is running.

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
- If the `markdown` package is available, renders the Markdown to HTML.
- If `markdown` is unavailable, the page falls back to the app's safe HTML rendering path.
- If `API_USAGE.md` is missing, the endpoint returns `404` with a short message.

---

### 4.3 Get All Users

- Method: `GET`
- Path: `/Users`
- Purpose: Read up to 100 items from the DynamoDB table using `scan`.

Example:

```http
GET http://localhost:5000/Users
```

Success response is typically a JSON array of items.

---

### 4.4 Get User By Email

- Method: `GET`
- Path: `/Users/<email>`
- Purpose: Fetch a user by email using the GSI.

Example:

```http
GET http://localhost:5000/Users/user2@example.com
```

Use URL encoding when needed:

- `#` becomes `%23`

Implementation note:

- This route queries `GSI1` with `KeyConditionExpression=Key('GSI1PK').eq(...)`.
- The app tries both raw email and `EMAIL#<email>` forms for consistency.
- `GSI1PK` is the email partition key, and `GSI1SK` is the user PK.

---

### 4.5 Get User By Id

- Method: `GET`
- Path: `/getUserById/<id>`
- Purpose: Fetch a user by id value in the URL.

Examples:

```http
GET http://localhost:5000/getUserById/USER%232
GET http://localhost:5000/getUserById/2
```

Implementation note:

- This route queries `GSI1` using the value in the URL as `GSI1PK`.
- Use it when the id value is stored in your GSI.

---

### 4.6 Create User

- Method: `POST`
- Path: `/Users`
- Purpose: Create a new user item with normalized key attributes.

#### Required fields

- `id`
- `email`

#### How keys are built

- `PK`:
  - if `id` starts with `USER#`, keep as-is
  - else set to `USER#<id>`
- `SK`:
  - if `SK` exists in request body, use it
  - else auto-generate with the current UTC timestamp (`...Z`)
- `GSI1PK`:
  - if `GSI1PK` exists in request body, use it
  - else set from email as `EMAIL#<email>` unless email already starts with `EMAIL#`
- `GSI1SK`:
  - always set to `PK`

#### Duplicate protection

The route writes using:

- `ConditionExpression='attribute_not_exists(PK) AND attribute_not_exists(SK)'`

This prevents creating the same `PK+SK` item twice.

#### Postman example

- Method: `POST`
- URL: `http://localhost:5000/Users`
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
curl -X POST "http://localhost:5000/Users" \
  -H "Content-Type: application/json" \
  -d '{"id":"2","email":"user2@example.com","name":"Test User 2","address":{"street":"200 Main St","city":"Metropolis","zip":"10002"}}'
```

#### Success response

- `statusCode`: `201`
- body: created item as JSON

If Cognito provisioning is enabled, the user is created in the user pool first and the DynamoDB write follows. If the Cognito step fails, the request is rejected before the DynamoDB item is stored.

#### Error responses

- `400` if:
  - body empty or not an object
  - `id` missing
  - `email` missing
- `409` if same `PK+SK` already exists
- `500` for unexpected AWS/client exceptions

---

### 4.7 Update User (Partial Update)

- Methods: `PATCH` or `PUT`
- Path: `/Users/<id>`
- Purpose: Update only provided attributes while keeping other attributes unchanged.

#### How target user is resolved

- If the path value looks like an email, the app searches by `GSI1PK`.
- Otherwise the id is normalized to `PK`:
  - if id starts with `USER#`, use as-is
  - else convert to `USER#<id>`
- The app resolves the item first, then updates the item using `{PK, SK}`.

#### Important restrictions

The API rejects updates to key attributes:

- `PK`
- `SK`

If any of these fields are included in the body, the response is `400`.

If the body includes `email` and does not include `GSI1PK`, the app also updates `GSI1PK` so the GSI stays aligned.

#### Request requirements

- `Content-Type: application/json`
- Body must be a non-empty JSON object.

#### Postman example

- Method: `PATCH`
- URL: `http://localhost:5000/Users/2`
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
curl -X PATCH "http://localhost:5000/Users/2" \
  -H "Content-Type: application/json" \
  -d '{"name":"Updated User Name","address":{"street":"201 Main St","city":"Cairo","zip":"10002"},"entityType":"User"}'
```

#### Success response

- `statusCode`: `200`
- body: updated item attributes as JSON

#### Error responses

- `400` if:
  - path id missing
  - body empty or not an object
  - forbidden key attributes included
- `404` if user does not exist for the resolved key
- `500` for unexpected AWS/client exceptions

## 5) Postman Quick Checklist

Before sending `POST /Users`:

1. Method must be `POST`.
2. URL must be `/Users`.
3. Header must include `Content-Type: application/json`.
4. Body must include at least `id` and `email`.

Before sending `PATCH /Users/<id>`:

1. Use the correct route (`/Users/...`), not `/getUserById/...`.
2. Method must be `PATCH` or `PUT`.
3. Header must include `Content-Type: application/json`.
4. Send update fields in the body, not URL params.
5. Keep `PK` and `SK` out of the request body.

## 6) Common Troubleshooting

### 405 Method Not Allowed

Cause:

- Sending `PATCH` to a GET-only route like `/getUserById/<id>`.

Fix:

- Use `PATCH /Users/<id>`.

### ValidationException: provided key element does not match schema

Cause:

- Using the wrong key shape for the table key schema.

Fix in current implementation:

- The app derives the correct `{PK, SK}` pair before `update_item`.

### Empty result when email/id includes `#`

Cause:

- `#` in a URL is treated as a fragment unless encoded.

Fix:

- Encode `#` as `%23`.

## 7) Data Model Notes

From the key definitions, table keys are:

- Partition key: `PK` (String)
- Sort key: `SK` (String)

GSI keys include:

- `GSI1PK`
- `GSI1SK`

When designing future routes:

- Use `query` for key-based searches and GSIs.
- Avoid `scan` for large tables whenever possible.

## 8) ECS / API Gateway Notes

- This app is designed to run as a normal Flask service in ECS behind an ALB.
- Responses should be returned as Flask JSON responses with real HTTP status codes.
- X-Ray is enabled through `XRayMiddleware`.
- For production tracing, make sure ECS has the required X-Ray permissions and network access.
