# DynamoDB Table Attributes Reference

This document summarizes the attributes used in the `onlineStore` DynamoDB table.

## 1) Table Key Attributes

These attributes define the table primary key and indexed keys.

| AttributeName | Type | Role |
|---|---|---|
| `PK` | `S` | Table partition key (HASH) |
| `SK` | `S` | Table sort key (RANGE) |
| `GSI1PK` | `S` | GSI1 partition key (HASH) |
| `GSI1SK` | `S` | GSI1 sort key (RANGE) |

## 2) Global Secondary Index (GSI1)

- Index name: `GSI1`
- Key schema:
  - `GSI1PK` (HASH)
  - `GSI1SK` (RANGE)
- Projection type: `INCLUDE`

Projected non-key attributes:

- `name`
- `address`
- `productName`
- `category`
- `description`
- `price`
- `supplierName`
- `orderStatus`
- `totalPrice`
- `items`
- `entityType`

## 3) Entity Attributes

### 3.1 User Attributes

| AttributeName | DataType | Description |
|---|---|---|
| `name` | `String` | The user's full name. |
| `address` | `Map` | A JSON object containing street, city, zip, etc. |

### 3.2 Product Attributes

| AttributeName | DataType | Description |
|---|---|---|
| `productName` | `String` | The name of the item being sold. |
| `category` | `String` | For example: Electronics, Clothing, Books. |
| `description` | `String` | Text describing the product. |
| `price` | `Number` | The cost of the product. |
| `supplierName` | `String` | The name of the product's supplier. |

### 3.3 Order Attributes

| AttributeName | DataType | Description |
|---|---|---|
| `orderStatus` | `String` | For example: Pending, Shipped, Delivered. |
| `totalPrice` | `Number` | The total cost of the entire order. |
| `items` | `List` | An array of Product IDs included in the purchase. |

### 3.4 Shared Attribute

| AttributeName | DataType | Description |
|---|---|---|
| `entityType` | `String` | Identifies the record type (`User`, `Product`, `Order`). |

## 4) Example Key Patterns (Common in this project)

These examples reflect your API usage pattern and can be adjusted as needed:

- User item:
  - `PK`: `USER#<id>`
  - `SK`: timestamp or user-specific value
  - `GSI1PK`: `EMAIL#<email>`
  - `GSI1SK`: `USER#<id>`

## 5) Notes

- Attribute type `S` means String in DynamoDB key schema definitions.
- Keep key attributes (`PK`, `SK`, `GSI1PK`, `GSI1SK`) stable after creation when possible.
- Use `entityType` consistently to simplify multi-entity table queries and filtering.
