
try: 
    from flask import Flask, request, render_template
    import json
    import boto3 
    import logging
    import os
    # import html
    # import re
    import sys
    from boto3.dynamodb.conditions import Key, Attr
    from decimal import Decimal
    from aws_xray_sdk.core import xray_recorder
    from aws_xray_sdk.ext.flask.middleware import XRayMiddleware
    from aws_xray_sdk.core import patch_all
    from botocore.exceptions import (
            ProfileNotFound,
            # NoRegionError,
            NoCredentialsError,
            PartialCredentialsError,
            EndpointConnectionError,
            ConnectTimeoutError,
            ReadTimeoutError,
            UnknownServiceError,
            ClientError

    )

except ModuleNotFoundError as e:
    print(f"Error: Required module not found - {e}")
    logging.error(f"Error: Required module not found - {e}")
    sys.exit(1)
 #######################################################################   

logger = logging.getLogger('Product_api')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s'
)

app = Flask(__name__)
try:
        session= boto3.Session()
        dynamodb_resource = session.resource('dynamodb')
        table_name = os.getenv('DYNAMODB_TABLE', 'onlineStore')
        table = dynamodb_resource.Table(table_name)

        credentials = session.get_credentials()

        if credentials is None:
            logger.info("  Credentials: NOT FOUND")
        else:
            logger.info(f"  Credentials source: {getattr(credentials, 'method', 'unknown')}")

except ProfileNotFound:
    logging.error("Error : AWS CLI profile not found. Please check the profile name.")
    sys.exit(1)
# except NoRegionError:
#     logging.error("Error : AWS region not specified. Use --region or set it in your config.")
#     sys.exit(1)
# aws will auto-detect region from env vars
except NoCredentialsError:
    logging.error("Error : AWS credentials not found. Please configure them using 'aws configure'.")
    sys.exit(1)
except PartialCredentialsError:
    logging.error("Error : Incomplete credentials. Please provide both Access Key and Secret Key.")
    sys.exit(1)
except EndpointConnectionError:
    logging.error("Error : Could not connect to AWS endpoint. Check your internet or region name.")
    sys.exit(1)
except ConnectTimeoutError:
    logging.error("Error : Connection to AWS timed out while trying to establish connection.")
    sys.exit(1)
except ReadTimeoutError:
    logging.error("Error : Connected, but AWS service didn't respond in time.")
    sys.exit(1)

except UnknownServiceError as e:
    logging.error(f"Error : UnknownServiceError: {e}. The service name might be incorrect or unsupported in this region.")
    sys.exit(1)

except ValueError as e:
    logging.error(f"Error : ValueError: {e}")
    sys.exit(1)

except Exception as e:
    logging.error(f"Error : Unexpected Error: {e}")
    sys.exit(1)
####################################################

# Configure X-Ray tracing (conditional for local development)
enable_xray = os.getenv('ENABLE_XRAY', 'false').lower() == 'true'
if enable_xray:
    logger.info("X-Ray tracing enabled")
    patch_all()
    xray_recorder.configure(service='Flask-API')
    XRayMiddleware(app, xray_recorder)
else:
    logger.info("X-Ray tracing disabled (set ENABLE_XRAY=true to enable)")


@app.route('/')
def health():
    logger.info('route=/ method=%s', request.method)
    return 'OK'


@app.route('/Products/<id>')
def get_product_by_id(id):
    logger.info('route=/Products/<id> method=%s id=%s', request.method, id)
    try:
        # PK pattern: PROD#<productid>
        product_pk = id if str(id).startswith('PROD#') else f'PROD#{id}'
        sk_arg = request.args.get('sk')
        if sk_arg:
            product_sk = sk_arg if str(sk_arg).startswith('SUPPLIER#') else f'SUPPLIER#{sk_arg}'
            response = table.query(
                KeyConditionExpression=Key('PK').eq(product_pk) & Key('SK').eq(product_sk)
            )
        else:
            response = table.query(
                KeyConditionExpression=Key('PK').eq(product_pk)
            )

        items = response.get('Items', [])

        filter_expression = None
        for key, value in request.args.items():
            if key == 'sk':
                continue
            condition = Attr(key).eq(value)
            filter_expression = condition if filter_expression is None else filter_expression & condition

        if filter_expression is not None:
            response = table.query(
                KeyConditionExpression=Key('PK').eq(product_pk)
                if not sk_arg
                else Key('PK').eq(product_pk) & Key('SK').eq(product_sk),
                FilterExpression=filter_expression,
            )
            items = response.get('Items', [])

        if not items:
            logger.info(
                'route=/Products/<id> found=false id=%s pk=%s sk_filter=%s attr_filters=%s',
                id,
                product_pk,
                sk_arg,
                [key for key in request.args.keys() if key != 'sk']
            )
            return create_response(404, {'message': f'Product {id} does not exist for the provided filters'})

        body = items[0] if len(items) == 1 else items
        logger.info(
            'route=/Products/<id> found=true id=%s pk=%s count=%s sk_filter=%s attr_filters=%s',
            id,
            product_pk,
            len(items),
            sk_arg,
            [key for key in request.args.keys() if key != 'sk']
        )
        return create_response(200, body)
    except ClientError as e:
        logger.exception('route=/Products/<id> aws_client_error id=%s', id)
        return create_response(500, {'message': str(e)})
    except Exception as e:
        logger.exception('route=/Products/<id> unexpected_error id=%s', id)
        return create_response(500, {'message': str(e)})


@app.route('/Products/category/<category>')
def get_all_products_by_category(category):
    logger.info('route=/Products/category/<category> method=%s category=%s', request.method, category)
    try:
        # GSI1PK pattern: CAT#<CATEGORY>
        if str(category).startswith('CAT#'):
            category_suffix = str(category)[4:]
        else:
            category_suffix = str(category)
        gsi1pk = f'CAT#{category_suffix.upper()}'

        status = request.args.get('status')
        key_expression = Key('GSI1PK').eq(gsi1pk)
        if status:
            key_expression = key_expression & Key('GSI1SK').begins_with(f'{str(status).upper()}#PRICE#')

        filter_expression = None
        for key, value in request.args.items():
            if key == 'status':
                continue
            condition = Attr(key).eq(value)
            filter_expression = condition if filter_expression is None else filter_expression & condition

        query_args = {
            'IndexName': 'GSI1',
            'KeyConditionExpression': key_expression,
        }
        if filter_expression is not None:
            query_args['FilterExpression'] = filter_expression

        response = table.query(**query_args)
        items = response.get('Items', [])

        logger.info(
            'route=/Products/category/<category> items_count=%s category=%s gsi1pk=%s status=%s attr_filters=%s',
            len(items),
            category,
            gsi1pk,
            status,
            [key for key in request.args.keys() if key != 'status']
        )
        return create_response(200, items)
    except ClientError as e:
        logger.exception('route=/Products/category/<category> aws_client_error category=%s', category)
        return create_response(500, {'message': str(e)})
    except Exception as e:
        logger.exception('route=/Products/category/<category> unexpected_error category=%s', category)
        return create_response(500, {'message': str(e)})

@app.route('/Products', methods=['POST'])
def create_product():
    payload = request.get_json(silent=True) or {}
    logger.info('route=/Products method=%s payload_keys=%s', request.method, list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__)

    if not isinstance(payload, dict) or not payload:
        return create_response(400, {'message': 'Request body must be a non-empty JSON object'})

    product_id = payload.get('id')
    supplier_name = payload.get('supplierName')
    category = payload.get('category')
    price = payload.get('price')
    productName = payload.get('productName')

    if not product_id:
        return create_response(400, {'message': 'id is required'})
    if not supplier_name:
        return create_response(400, {'message': 'supplierName is required'})
    if not category:
        return create_response(400, {'message': 'category is required'})
    if price is None:
        return create_response(400, {'message': 'price is required'})

    product_pk = product_id if str(product_id).startswith('PROD#') else f'PROD#{product_id}'
    product_sk = supplier_name if str(supplier_name).startswith('SUPPLIER#') else f'SUPPLIER#{supplier_name}'
    gsi1pk = category if str(category).startswith('CAT#') else f'CAT#{str(category).upper()}'

    try:
        price_value = price if isinstance(price, Decimal) else Decimal(str(price))
    except Exception:
        return create_response(400, {'message': 'price must be a valid number'})

    status_value = payload.get('status', 'AVAILABLE')
    productName = payload.get('productName', '')
    price_text = f'{price_value:.2f}'.zfill(8)
    gsi1sk = f'{str(status_value).upper()}#PRICE#{price_text}'

    item = {
        'PK': product_pk,
        'SK': product_sk,
        'GSI1PK': gsi1pk,
        'GSI1SK': gsi1sk,
        'entityType': payload.get('entityType', 'Product'),
        'productName': productName,
        'supplierName': supplier_name,
        'category': category,
        'price': price_value,
        'status': status_value,
    }

    for key, value in payload.items():
        if key in {'PK', 'SK', 'GSI1PK', 'GSI1SK'}:
            continue
        if key in {'productName', 'id', 'supplierName', 'category', 'price', 'status', 'entityType'}:
            continue
        item[key] = _sanitize_dynamodb_value(value)

    try:
        table.put_item(
            Item=item,
            ConditionExpression='attribute_not_exists(PK) AND attribute_not_exists(SK)'
        )
        logger.info('route=/Products method=%s created=true pk=%s sk=%s gsi1pk=%s gsi1sk=%s', request.method, product_pk, product_sk, gsi1pk, gsi1sk)
        return create_response(201, item)
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            logger.warning('route=/Products method=%s duplicate=true pk=%s sk=%s', request.method, product_pk, product_sk)
            return create_response(409, {'message': f'Product with PK {product_pk} and SK {product_sk} already exists'})
        logger.exception('route=/Products method=%s aws_client_error pk=%s sk=%s', request.method, product_pk, product_sk)
        return create_response(500, {'message': str(e)})
    except Exception as e:
        logger.exception('route=/Products method=%s unexpected_error pk=%s sk=%s', request.method, product_pk, product_sk)
        return create_response(500, {'message': str(e)})


def _sanitize_dynamodb_value(value):
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _sanitize_dynamodb_value(inner_value) for key, inner_value in value.items()}
    if isinstance(value, list):
        return [_sanitize_dynamodb_value(item) for item in value]
    return value


@app.route('/Products/<id>', methods=['PATCH', 'PUT'])
def update_product(id):
    fields = request.get_json(silent=True) or {}
    logger.info('route=/Products/<id> method=%s id=%s payload_keys=%s', request.method, id, list(fields.keys()) if isinstance(fields, dict) else type(fields).__name__)

    if not id:
        return create_response(400, {'message': 'product id path parameter is required'})

    if not isinstance(fields, dict) or not fields:
        return create_response(400, {'message': 'Request body must be a non-empty JSON object'})

    forbidden = {'PK', 'SK', 'GSI1PK', 'GSI1SK', 'supplierName'}
    blocked = [key for key in fields.keys() if key in forbidden]
    if blocked:
        return create_response(400, {'message': f'Cannot update key attributes directly: {", ".join(blocked)}'})

    try:
        product_pk = id if str(id).startswith('PROD#') else f'PROD#{id}'
        supplier_arg = request.args.get('sk') or request.args.get('supplierName')

        if supplier_arg:
            product_sk = supplier_arg if str(supplier_arg).startswith('SUPPLIER#') else f'SUPPLIER#{supplier_arg}'
            lookup = table.query(
                KeyConditionExpression=Key('PK').eq(product_pk) & Key('SK').eq(product_sk),
                Limit=1
            )
        else:
            lookup = table.query(
                KeyConditionExpression=Key('PK').eq(product_pk)
            )

        items = lookup.get('Items', [])
        if not items:
            return create_response(404, {'message': f'Product {id} does not exist'})

        if len(items) > 1 and not supplier_arg:
            return create_response(400, {'message': 'Multiple products share this id; provide sk or supplierName query parameter to select the supplier record'})

        item = items[0]
        current_supplier_sk = item.get('SK')
        if not current_supplier_sk:
            return create_response(500, {'message': 'Matched product record is missing SK'})

        normalized_fields = {key: _sanitize_dynamodb_value(value) for key, value in fields.items()}
        updated_item = dict(item)
        updated_item.update(normalized_fields)

        expression_attribute_names = {}
        expression_attribute_values = {}
        set_clauses = []

        for i, (key, value) in enumerate(normalized_fields.items()):
            name_key = f'#k{i}'
            value_key = f':v{i}'
            expression_attribute_names[name_key] = key
            expression_attribute_values[value_key] = value
            set_clauses.append(f'{name_key} = {value_key}')

        if 'category' in normalized_fields:
            gsi1pk_value = f'CAT#{str(updated_item["category"]).upper()}'
            expression_attribute_names['#gsi1pk'] = 'GSI1PK'
            expression_attribute_values[':gsi1pk'] = gsi1pk_value
            set_clauses.append('#gsi1pk = :gsi1pk')

        if 'status' in normalized_fields or 'price' in normalized_fields:
            status_value = updated_item.get('status', item.get('status'))
            price_value = updated_item.get('price', item.get('price'))
            if status_value is not None and price_value is not None:
                if not isinstance(price_value, Decimal):
                    price_value = Decimal(str(price_value))
                price_text = f'{price_value:.2f}'.zfill(8)
                gsi1sk_value = f'{str(status_value).upper()}#PRICE#{price_text}'
                expression_attribute_names['#gsi1sk'] = 'GSI1SK'
                expression_attribute_values[':gsi1sk'] = gsi1sk_value
                set_clauses.append('#gsi1sk = :gsi1sk')

        response = table.update_item(
            Key={'PK': product_pk, 'SK': current_supplier_sk},
            UpdateExpression='SET ' + ', '.join(set_clauses),
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values,
            ConditionExpression='attribute_exists(PK) AND attribute_exists(SK)',
            ReturnValues='ALL_NEW'
        )

        logger.info(
            'route=/Products/<id> method=%s updated=true id=%s pk=%s sk=%s payload_keys=%s',
            request.method,
            id,
            product_pk,
            current_supplier_sk,
            list(fields.keys())
        )
        return create_response(200, response.get('Attributes', {}))

    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            logger.warning('route=/Products/<id> method=%s not_found=true id=%s', request.method, id)
            return create_response(404, {'message': f'Product {id} does not exist'})
        logger.exception('route=/Products/<id> method=%s aws_client_error id=%s', request.method, id)
        return create_response(500, {'message': str(e)})
    except Exception as e:
        logger.exception('route=/Products/<id> method=%s unexpected_error id=%s', request.method, id)
        return create_response(500, {'message': str(e)})


@app.route('/Products/help')
def help_page():
    logger.info('route=/Products/help method=%s', request.method)
    docs_path = os.path.join(os.path.dirname(__file__), 'API_USAGE.md')

    if not os.path.exists(docs_path):
        logger.warning('route=/Products/help docs_missing path=%s', docs_path)
        return (
            '<h1>API Help</h1><p>API_USAGE.md was not found in the project folder.</p>',
            404,
        )

    with open(docs_path, 'r', encoding='utf-8') as f:
        markdown_text = f.read()

    try:
        md = __import__('markdown')
        content_html = md.markdown(
            markdown_text,
            extensions=['fenced_code', 'tables', 'toc']
        )
    except Exception:
        logger.info('route=/Products/help markdown_package_not_available_using_fallback=true')
        # content_html = _render_markdown_fallback(markdown_text)
    return render_template('help.html', content_html=content_html)


def create_response(status_code, body):
    # Normalize Decimal and other non-JSON-native values first
    payload = json.dumps(
        body,
        default=lambda x: float(x) if isinstance(x, Decimal) else str(x)
    )

    response = app.response_class(
        response=payload,
        status=status_code,
        mimetype='application/json'
    )
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


if __name__ == '__main__':
    app.run(debug=True)


