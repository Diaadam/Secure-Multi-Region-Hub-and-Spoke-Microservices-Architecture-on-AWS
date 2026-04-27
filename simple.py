try: 
    from flask import Flask, request, render_template
    import json
    import boto3 
    import logging
    import os
    # import html
    # import re
    import sys
    from boto3.dynamodb.conditions import Key
    from decimal import Decimal
    from botocore.exceptions import (
            ProfileNotFound,
            NoRegionError,
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

logger = logging.getLogger('user_api')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s'
)

app = Flask(__name__)
try:
        session= boto3.Session()
        dynamodb_resource = session.resource('dynamodb')
        table = dynamodb_resource.Table('onlineStore')

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




@app.route('/')
def health():
    logger.info('route=/ method=%s', request.method)
    return 'OK'



@app.route('/getAllUsers')
def get_all_users():
    logger.info('route=/getAllUsers method=%s', request.method)
    try:
        response = table.scan()
        body = response['Items']
        logger.info('route=/getAllUsers items_count=%s', len(body))
        return create_response(200, body)
    except ClientError as e:
        logger.exception('route=/getAllUsers aws_client_error')
        return create_response(500, {'message': str(e)})
    except Exception as e:
        logger.exception('route=/getAllUsers unexpected_error')
        return create_response(500, {'message': str(e)})

@app.route('/getUserByEmail/<email>')
def get_user_by_email(email):
    logger.info('route=/getUserByEmail method=%s email=%s', request.method, email)
    try:
        response = table.get_item(
            IndexName='GSI1',
            KeyConditionExpression=Key('GSI1PK').eq(email)
        )
        body = response['Item'] if 'Item' in response else None
        logger.info('route=/getUserByEmail found=%s', body is not None)
        return create_response(200, body)
    except ClientError as e:
        logger.exception('route=/getUserByEmail aws_client_error email=%s', email)
        return create_response(500, {'message': str(e)})
    except Exception as e:
        logger.exception('route=/getUserByEmail unexpected_error email=%s', email)
        return create_response(500, {'message': str(e)})

@app.route('/getUserById/<id>')
def get_user_by_id(id):
    logger.info('route=/getUserById method=%s id=%s', request.method, id)
    try:
        response = table.get_item(
            IndexName='GSI1',
            KeyConditionExpression=Key('GSI1PK').eq(id)
        )
        body = response['Item'] if 'Item' in response else None
        logger.info('route=/getUserById found=%s id=%s', body is not None, id)
        return create_response(200, body)
    except ClientError as e:
        logger.exception('route=/getUserById aws_client_error id=%s', id)
        return create_response(500, {'message': str(e)})
    except Exception as e:
        logger.exception('route=/getUserById unexpected_error id=%s', id)
        return create_response(500, {'message': str(e)})


@app.route('/createUser', methods=['POST'])
def create_user():
    from datetime import datetime

    payload = request.get_json(silent=True) or {}
    logger.info('route=/createUser method=%s payload_keys=%s', request.method, list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__)
    if not isinstance(payload, dict) or not payload:
        return create_response(400, {'message': 'Request body must be a non-empty JSON object'})

    raw_id = payload.get('id')
    email = payload.get('email')

    if not raw_id:
        return create_response(400, {'message': 'id is required'})
    if not email:
        return create_response(400, {'message': 'email is required'})

    user_pk = raw_id if str(raw_id).startswith('USER#') else f'USER#{raw_id}'
    user_sk = payload.get('SK') or (datetime.utcnow().isoformat() + 'Z')

    gsi1pk = payload.get('GSI1PK')
    if not gsi1pk:
        gsi1pk = email if str(email).startswith('EMAIL#') else f'EMAIL#{email}'

    item = {
        'PK': user_pk,
        'SK': user_sk,
        'GSI1PK': gsi1pk,
        'GSI1SK': user_pk,
        'entityType': payload.get('entityType', 'User'),
        'email': email
    }

    for key, value in payload.items():
        if key in {'PK', 'SK', 'GSI1PK', 'GSI1SK'}:
            continue
        if key == 'id':
            continue
        item[key] = value

    try:
        table.put_item(
            Item=item,
            ConditionExpression='attribute_not_exists(PK) AND attribute_not_exists(SK)'
        )
        logger.info('route=/createUser created=true pk=%s sk=%s', user_pk, user_sk)
        return create_response(201, item)
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            logger.warning('route=/createUser duplicate=true pk=%s sk=%s', user_pk, user_sk)
            return create_response(409, {'message': f'User with PK {user_pk} and SK {user_sk} already exists'})
        logger.exception('route=/createUser aws_client_error pk=%s sk=%s', user_pk, user_sk)
        return create_response(500, {'message': str(e)})
    except Exception as e:
        logger.exception('route=/createUser unexpected_error pk=%s sk=%s', user_pk, user_sk)
        return create_response(500, {'message': str(e)})


@app.route('/updateUser/<id>', methods=['PATCH', 'PUT'])
def update_user(id):
    fields = request.get_json(silent=True) or {}
    logger.info('route=/updateUser method=%s id=%s payload_keys=%s', request.method, id, list(fields.keys()) if isinstance(fields, dict) else type(fields).__name__)

    if not id:
        return create_response(400, {'message': 'user id path parameter is required'})

    if not isinstance(fields, dict) or not fields:
        return create_response(400, {'message': 'Request body must be a non-empty JSON object'})

    # Do not allow key attributes to be changed.
    forbidden = {'PK', 'SK'}
    blocked = [k for k in fields.keys() if k in forbidden]
    if blocked:
        return create_response(400, {'message': f'Cannot update key attributes: {", ".join(blocked)}'})

    # Build the user's PK from path id, no table scan.
    # If your id already comes as USER#2, keep it as-is.
    user_pk = id if id.startswith('USER#') else f'USER#{id}'

    try:
        # One record per user: fetch that one record by PK (table query, not scan).
        lookup = table.query(
            KeyConditionExpression=Key('PK').eq(user_pk),
            Limit=1
        )
        items = lookup.get('Items', [])
        if not items:
            return create_response(404, {'message': f'User with PK {user_pk} does not exist'})

        item = items[0]
        sk = item.get('SK')
        if not sk:
            return create_response(500, {'message': 'Matched user record is missing SK'})

        expression_attribute_names = {}
        expression_attribute_values = {}
        set_clauses = []

        for i, (key, value) in enumerate(fields.items()):
            name_key = f'#k{i}'
            value_key = f':v{i}'
            expression_attribute_names[name_key] = key
            expression_attribute_values[value_key] = value
            set_clauses.append(f'{name_key} = {value_key}')

        response = table.update_item(
            Key={'PK': user_pk, 'SK': sk},
            UpdateExpression='SET ' + ', '.join(set_clauses),
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values,
            ConditionExpression='attribute_exists(PK) AND attribute_exists(SK)',
            ReturnValues='ALL_NEW'
        )
        logger.info('route=/updateUser updated=true id=%s pk=%s', id, user_pk)
        return create_response(200, response.get('Attributes', {}))

    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            logger.warning('route=/updateUser not_found=true id=%s pk=%s', id, user_pk)
            return create_response(404, {'message': f'User with PK {user_pk} does not exist'})
        logger.exception('route=/updateUser aws_client_error id=%s pk=%s', id, user_pk)
        return create_response(500, {'message': str(e)})
    except Exception as e:
        logger.exception('route=/updateUser unexpected_error id=%s pk=%s', id, user_pk)
        return create_response(500, {'message': str(e)})


@app.route('/help')
def help_page():
    logger.info('route=/help method=%s', request.method)
    docs_path = os.path.join(os.path.dirname(__file__), 'API_USAGE.md')

    if not os.path.exists(docs_path):
        logger.warning('route=/help docs_missing path=%s', docs_path)
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
        logger.info('route=/help markdown_package_not_available_using_fallback=true')
        # content_html = _render_markdown_fallback(markdown_text)
    return render_template('help.html', content_html=content_html)


def create_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type"
        },
        "body": json.dumps(body, default=lambda x: float(x) if isinstance(x, Decimal) else str(x))
    }

# def _render_markdown_fallback(markdown_text):
#     lines = markdown_text.splitlines()
#     parts = []
#     in_code = False
#     in_ul = False
#     in_ol = False

#     def close_lists():
#         nonlocal in_ul, in_ol
#         if in_ul:
#             parts.append('</ul>')
#             in_ul = False
#         if in_ol:
#             parts.append('</ol>')
#             in_ol = False

#     def inline_text(value):
#         safe = html.escape(value)
#         return re.sub(r'`([^`]+)`', r'<code>\1</code>', safe)

#     for raw_line in lines:
#         line = raw_line.rstrip('\n')
#         stripped = line.strip()

#         if stripped.startswith('```'):
#             close_lists()
#             if not in_code:
#                 parts.append('<pre><code>')
#                 in_code = True
#             else:
#                 parts.append('</code></pre>')
#                 in_code = False
#             continue

#         if in_code:
#             parts.append(html.escape(line) + '\n')
#             continue

#         if not stripped:
#             close_lists()
#             continue

#         heading_match = re.match(r'^(#{1,6})\s+(.*)$', stripped)
#         if heading_match:
#             close_lists()
#             level = len(heading_match.group(1))
#             parts.append(f'<h{level}>{inline_text(heading_match.group(2))}</h{level}>')
#             continue

#         ordered_match = re.match(r'^\d+\.\s+(.*)$', stripped)
#         if ordered_match:
#             if not in_ol:
#                 close_lists()
#                 parts.append('<ol>')
#                 in_ol = True
#             parts.append(f'<li>{inline_text(ordered_match.group(1))}</li>')
#             continue

#         if stripped.startswith('- '):
#             if not in_ul:
#                 close_lists()
#                 parts.append('<ul>')
#                 in_ul = True
#             parts.append(f'<li>{inline_text(stripped[2:])}</li>')
#             continue

#         close_lists()
#         parts.append(f'<p>{inline_text(stripped)}</p>')

#     close_lists()
#     if in_code:
#         parts.append('</code></pre>')

#     return ''.join(parts)



if __name__ == '__main__':
    app.run(debug=True)


