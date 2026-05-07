# Flask Products API - Detailed Usage Guide

This guide explains how to run and use the API implemented in `unified_Products.py`.

## 1) Overview

Base URL when running locally:

- `http://localhost:5000`

Current implemented endpoints:

- `GET /`
- `GET /Products/<id>`
- `GET /Products/category/<category>`
- `POST /Products`
- `PATCH /Products/<id>`
- `PUT /Products/<id>`

## 2) Run The API

From the Products project folder:

```powershell
python unified_Products.py
```

Flask will start in debug mode and listen on port 5000 by default.

## 3) Response Format

All handlers return a real Flask JSON response with the HTTP status code set on the response itself.

Important notes:

- The body is returned as JSON, not as a Lambda-style `{ statusCode, headers, body }` envelope.
- CORS headers are added by the application response helper.
- If you are using Postman or curl, read the response body directly as JSON.
- Decimal values are normalized to floats in JSON output.

## 4) DynamoDB Key Schema

Products use a single-table design with these key patterns:

- **PK**: `PROD#<productid>` — Product partition key
- **SK**: `SUPPLIER#<suppliername>` — Supplier sort key (allows multiple suppliers per product)
- **GSI1PK**: `CAT#<CATEGORY>` — Category partition key for category-based queries
- **GSI1SK**: `<STATUS>#PRICE#<zero-padded-price>` — Status and price for sorting (e.g., `AVAILABLE#PRICE#00299.00`)

## 5) Endpoints In Detail

### 5.1 Health Check

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

### 5.2 Get Product By Id

- Method: `GET`
- Path: `/Products/<id>`
- Purpose: Fetch one or more products by product id using the PK.

#### Query parameters (optional)

- `sk=<suppliername>` — Filter by supplier (e.g., `?sk=acme`)
- Any other attribute field (e.g., `?category=electronics&price=299.00`) — Filter by non-key attributes

#### Key normalization

- If `<id>` does not start with `PROD#`, the app prepends it: `PROD#<id>`
- If `sk` is provided and does not start with `SUPPLIER#`, the app prepends it: `SUPPLIER#<sk>`

Examples:

```http
GET http://localhost:5000/Products/1
GET http://localhost:5000/Products/PROD%231
GET http://localhost:5000/Products/1?sk=Supplier%20A
GET http://localhost:5000/Products/3?sk=Supplier%20B&category=Electronics
GET http://localhost:5000/Products/9?price=14.99
```

#### Success response

- `statusCode`: `200`
- body: single product item (if one match) or array of items (if multiple matches)

#### Error responses

- `404` if no product matches the id and filters
- `500` for unexpected AWS/client exceptions

---

### 5.3 Get Products By Category

- Method: `GET`
- Path: `/Products/category/<category>`
- Purpose: Fetch all products in a category using the GSI.

#### Query parameters (optional)

- `status=<status>` — Filter by status in the GSI1SK sort key (e.g., `?status=available`). Matches records where GSI1SK starts with `<STATUS>#PRICE#`
- Any other attribute field (e.g., `?supplierName=acme&price=100.00`) — Filter by non-key attributes

#### Category normalization

- If `<category>` does not start with `CAT#`, the app converts to uppercase and prepends: `CAT#<CATEGORY>`

Examples:

```http
GET http://localhost:5000/Products/category/books
GET http://localhost:5000/Products/category/CAT%23BOOKS
GET http://localhost:5000/Products/category/electronics?status=available
GET http://localhost:5000/Products/category/electronics?status=available&supplierName=Supplier%20B
GET http://localhost:5000/Products/category/clothing?price=83.99
```

#### Success response

- `statusCode`: `200`
- body: JSON array of product items

#### Error responses

- `500` for unexpected AWS/client exceptions

---

### 5.4 Create Product

- Method: `POST`
- Path: `/Products`
- Purpose: Create a new product item with normalized key attributes.

#### Required fields

- `id` — The product identifier
- `supplierName`
- `category`
- `price`

#### Optional fields

- `productName` — Human-readable product name (defaults to empty string)
- `status` — Product status (defaults to `AVAILABLE`)
- `entityType` — Entity type (defaults to `Product`)
- Any other custom attributes

#### How keys are built

- **PK**:
  - if `id` starts with `PROD#`, keep as-is
  - else set to `PROD#<id>`
- **SK**:
  - if `supplierName` starts with `SUPPLIER#`, keep as-is
  - else set to `SUPPLIER#<supplierName>`
- **GSI1PK**:
  - if `category` starts with `CAT#`, keep as-is
  - else set to `CAT#<CATEGORY>` (uppercase)
- **GSI1SK**:
  - Use `status` from request (default: `AVAILABLE`)
  - Convert price to Decimal with 2 decimal places, zero-padded to 8 characters
  - Format: `<STATUS>#PRICE#<zero-padded-price>` (e.g., `AVAILABLE#PRICE#00299.00`)

#### Duplicate protection

The route writes using:

- `ConditionExpression='attribute_not_exists(PK) AND attribute_not_exists(SK)'`

This prevents creating the same `PK+SK` item twice.

#### Postman example

- Method: `POST`
- URL: `http://localhost:5000/Products`
- Headers: `Content-Type: application/json`
- Body:

```json
{
  "id": "101",
  "supplierName": "acme",
  "category": "electronics",
  "price": 299.99,
  "productName": "Widget Pro",
  "status": "AVAILABLE",
  "description": "High-quality widget with advanced features",
  "entityType": "Product"
}
```

Equivalent curl:

```bash
curl -X POST "http://localhost:5000/Products" \
  -H "Content-Type: application/json" \
  -d '{"id":"11","supplierName":"Supplier A","category":"Electronics","price":129.99,"productName":"Wireless Headphones","status":"AVAILABLE","description":"Premium noise-cancelling wireless headphones with 30-hour battery life","entityType":"Product"}'
```

#### Success response

- `statusCode`: `201`
- body: created item as JSON

#### Error responses

- `400` if:
  - body empty or not an object
  - `id` missing
  - `supplierName` missing
  - `category` missing
  - `price` missing or not a valid number
- `409` if same `PK+SK` (product id + supplier) already exists
- `500` for unexpected AWS/client exceptions

---

### 5.5 Update Product (Partial Update)

- Methods: `PATCH` or `PUT`
- Path: `/Products/<id>`
- Purpose: Update only provided attributes while keeping other attributes unchanged.

#### Query parameters (optional)

- `sk=<suppliername>` or `supplierName=<suppliername>` — Select the supplier record when multiple suppliers exist for the same product id

#### How target product is resolved

- The path value is normalized to `PK`:
  - if id starts with `PROD#`, use as-is
  - else convert to `PROD#<id>`
- If multiple products share the same id (different suppliers), you must provide `sk` or `supplierName` query param to select one.
- The app resolves the item first, then updates using `{PK, SK}`.

#### Important restrictions

The API rejects updates to key attributes:

- `PK`
- `SK`
- `GSI1PK` (use `category` instead; the route recalculates this when `category` changes)
- `GSI1SK` (use `status` or `price` instead; the route recalculates this when they change)
- `supplierName` (immutable after creation)

If any of these fields are included in the body, the response is `400`.

#### Automatic GSI synchronization

- If `category` is updated, `GSI1PK` is automatically recalculated to `CAT#<CATEGORY>`
- If `status` or `price` is updated, `GSI1SK` is automatically recalculated to `<STATUS>#PRICE#<zero-padded-price>`

#### Request requirements

- `Content-Type: application/json`
- Body must be a non-empty JSON object.

#### Postman example

- Method: `PATCH`
- URL: `http://localhost:5000/Products/3?sk=Supplier%20B`
- Headers: `Content-Type: application/json`
- Body:

```json
{
  "price": 54.99,
  "status": "ON_SALE",
  "productName": "Updated Electronics Item 3",
  "description": "Now with advanced features and better performance"
}
```

Equivalent curl:

```bash
curl -X PATCH "http://localhost:5000/Products/3?sk=Supplier%20B" \
  -H "Content-Type: application/json" \
  -d '{"price":54.99,"status":"ON_SALE","productName":"Updated Electronics Item 3","description":"Now with advanced features and better performance"}'
```

#### Success response

- `statusCode`: `200`
- body: updated item attributes as JSON

#### Error responses

- `400` if:
  - path id missing
  - body empty or not an object
  - forbidden key attributes included (PK, SK, GSI1PK, GSI1SK, supplierName)
  - multiple products exist for this id and no `sk`/`supplierName` provided
- `404` if product does not exist for the resolved key
- `500` for unexpected AWS/client exceptions

---

## 6) Postman Quick Checklist

Before sending `POST /Products`:

1. Method must be `POST`.
2. URL must be `/Products`.
3. Header must include `Content-Type: application/json`.
4. Body must include at least `id`, `supplierName`, `category`, and `price`.

Before sending `PATCH /Products/<id>`:

1. Use the correct route (`/Products/...`), not `/Products/category/...`.
2. Method must be `PATCH` or `PUT`.
3. Header must include `Content-Type: application/json`.
4. Send update fields in the body, not URL params.
5. Keep `PK`, `SK`, `GSI1PK`, `GSI1SK`, and `supplierName` out of the request body.
6. If multiple suppliers exist for the same product id, include `sk=Supplier%20Name` query parameter (URL-encode spaces as `%20`).

---

## 7) Common Troubleshooting

### 405 Method Not Allowed

Cause:

- Sending `PATCH` to a GET-only route like `/Products/category/<category>`.

Fix:

- Use `PATCH /Products/<id>` for updates.

### 409 Conflict (Product already exists)

Cause:

- Attempting to `POST` a product with the same `productid` and `supplierName` combination that already exists.

Fix:

- Use a different `productid` or `supplierName`, or use `PATCH` to update an existing product.

### 400 Bad Request (Multiple products share this id)

Cause:

- Using `PATCH /Products/<id>` when multiple suppliers have this product id, but not providing `sk` or `supplierName` to select which one to update.

Fix:

- Include `?sk=Supplier%20Name` query parameter in the URL (spaces must be URL-encoded as `%20`).

### URL Encoding for Spaces and Special Characters

Cause:

- Special characters like `#` or spaces in parameters (supplier names, categories) need URL encoding.

Fix:

- Encode space as `%20`, `#` as `%23`, etc. Example: "Supplier A" → `Supplier%20A`

---

## 8) Data Model Notes

From the key definitions, table keys are:

- Partition key: `PK` (String)
- Sort key: `SK` (String)

GSI1 keys:

- Partition key: `GSI1PK` (String)
- Sort key: `GSI1SK` (String)

When designing future routes:

- Use `query` for key-based searches and GSIs.
- Avoid `scan` for large tables whenever possible.
- Status values are normalized to uppercase in the GSI1SK.
- Prices are always stored as two-decimal Decimal values, zero-padded to 8 characters in GSI1SK for proper sorting.

---

## 9) ECS / API Gateway Notes

- This app is designed to run as a normal Flask service in ECS behind an ALB.
- Responses are returned as Flask JSON responses with real HTTP status codes.
- X-Ray is enabled through `XRayMiddleware`.
- For production tracing, make sure ECS has the required X-Ray permissions and network access.
